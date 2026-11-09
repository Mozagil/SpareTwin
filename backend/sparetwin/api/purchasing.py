"""Satınalma (Faz 2): tedarikçi, talep → sipariş → teslim alma, ihtiyaç önerisi.

Yetki: listeleme herkes; talep açma, düzenleme ve teslim alma teknisyen ve üstü;
sipariş verme, iptal ve tedarikçi yönetimi yönetici (manager) ve üstü.
Kurallar (durum geçişleri, kalan miktar, stok/parça girişi) veritabanı fonksiyonlarında (0014).
"""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, model_validator

from .deps import TenantCtx

router = APIRouter(prefix="/purchasing", tags=["Satınalma"])

PoStatus = Literal["draft", "ordered", "partial", "received", "cancelled"]


# ---------- Tedarikçi ----------
class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact_name: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=120)
    tax_no: str | None = Field(None, max_length=40)
    address: str | None = Field(None, max_length=400)
    notes: str | None = Field(None, max_length=1000)
    lead_time_days: int | None = Field(None, ge=0, le=365, description="Tipik teslim süresi")
    is_active: bool = True


SUPPLIER_COLS = "id, name, contact_name, phone, email, tax_no, address, notes, lead_time_days, is_active, created_at"


@router.get("/suppliers", summary="Tedarikçiler")
def suppliers(ctx: TenantCtx, include_inactive: bool = False):
    with ctx.tx() as conn:
        return conn.execute(
            f"""select {SUPPLIER_COLS},
                       (select count(*) from public.purchase_orders o
                         where o.supplier_id = s.id and o.status in ('ordered', 'partial')) as open_orders
                  from public.suppliers s
                 where s.tenant_id = %s and (%s or s.is_active)
                 order by s.is_active desc, s.name""",
            [ctx.tenant_id, include_inactive],
        ).fetchall()


@router.post("/suppliers", status_code=201, summary="Tedarikçi ekle")
def supplier_create(body: SupplierIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        return conn.execute(
            f"""insert into public.suppliers (tenant_id, name, contact_name, phone, email, tax_no, address, notes, lead_time_days, is_active)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning {SUPPLIER_COLS}""",
            [ctx.tenant_id, body.name, body.contact_name, body.phone, body.email, body.tax_no, body.address,
             body.notes, body.lead_time_days, body.is_active],
        ).fetchone()


@router.patch("/suppliers/{supplier_id}", summary="Tedarikçi güncelle (pasife alma dahil)")
def supplier_update(supplier_id: UUID, body: SupplierIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        row = conn.execute(
            f"""update public.suppliers
                   set name = %s, contact_name = %s, phone = %s, email = %s, tax_no = %s, address = %s, notes = %s,
                       lead_time_days = %s, is_active = %s
                 where id = %s and tenant_id = %s returning {SUPPLIER_COLS}""",
            [body.name, body.contact_name, body.phone, body.email, body.tax_no, body.address, body.notes,
             body.lead_time_days, body.is_active, supplier_id, ctx.tenant_id],
        ).fetchone()
        if not row:
            raise HTTPException(404, "Tedarikçi bulunamadı")
        return row


# ---------- İhtiyaç önerisi ----------
@router.get("/needs", summary="Sipariş ihtiyacı: yaklaşan değişim + kritik seviye − stok − siparişte")
def needs(ctx: TenantCtx):
    with ctx.tx() as conn:
        return conn.execute(
            """select * from public.v_purchase_needs where tenant_id = %s
                order by need desc, upcoming desc, name""",
            [ctx.tenant_id],
        ).fetchall()


# ---------- Sipariş ----------
class LineIn(BaseModel):
    part_id: UUID
    qty: Decimal = Field(gt=0, le=1_000_000)
    unit_cost: Decimal | None = Field(None, ge=0, description="Birim fiyat; boşsa katalog / ortalama fiyat")
    asset_id: UUID | None = Field(None, description="Hangi makine için (bilgi amaçlı)")
    notes: str | None = Field(None, max_length=300)


class OrderIn(BaseModel):
    supplier_id: UUID | None = None
    site_id: UUID | None = Field(None, description="Teslimat deposu")
    expected_at: date | None = None
    notes: str | None = Field(None, max_length=1000)
    lines: list[LineIn] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _unique_parts(self):
        ids = [ln.part_id for ln in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Aynı kalem listede birden fazla kez var; miktarları birleştirin")
        return self


class OrderPatch(BaseModel):
    supplier_id: UUID | None = None
    site_id: UUID | None = None
    expected_at: date | None = None
    notes: str | None = Field(None, max_length=1000)
    lines: list[LineIn] | None = Field(None, min_length=1, max_length=100, description="Verilirse satırlar tümden değişir (yalnızca talep durumunda)")

    @model_validator(mode="after")
    def _unique_parts(self):
        if self.lines:
            ids = [ln.part_id for ln in self.lines]
            if len(ids) != len(set(ids)):
                raise ValueError("Aynı kalem listede birden fazla kez var; miktarları birleştirin")
        return self


class StatusIn(BaseModel):
    status: Literal["ordered", "cancelled", "received"] = Field(
        description="ordered: sipariş ver, cancelled: iptal, received: kısmi teslimatın kalanını kapat")


class ReceiveLine(BaseModel):
    line_id: int
    qty: Decimal = Field(gt=0, le=1_000_000)
    serials: list[dict[str, str | None]] | None = Field(
        None, max_length=100, description="Seri numaralı kalemde her adet için {serial_no, qr_code}")


class ReceiveIn(BaseModel):
    site_id: UUID | None = Field(None, description="Boşsa siparişin teslimat deposu")
    ref: str | None = Field(None, max_length=60, description="İrsaliye / fatura no")
    lines: list[ReceiveLine] = Field(min_length=1, max_length=100)


ORDER_LIST_SQL = """
select o.id, o.number, o.status, o.supplier_id, s.name as supplier_name, o.site_id, st.name as site_name,
       o.expected_at, o.notes, o.ordered_at, o.closed_at, o.created_at, o.updated_at,
       ru.full_name as requested_by_name, ou.full_name as ordered_by_name,
       l.line_count, l.total, l.received_total, l.summary,
       (o.status in ('ordered', 'partial') and o.expected_at < current_date) as late
  from public.purchase_orders o
  left join public.suppliers s on s.id = o.supplier_id
  left join public.sites st on st.id = o.site_id
  left join public.app_users ru on ru.id = o.requested_by
  left join public.app_users ou on ou.id = o.ordered_by
  left join lateral (
    select count(*) as line_count,
           sum(pl.qty * coalesce(pl.unit_cost, p.list_cost, 0)) as total,
           sum(pl.received_qty * coalesce(pl.unit_cost, p.list_cost, 0)) as received_total,
           string_agg(trim_scale(pl.qty)::text || ' ' || p.unit || ' ' || p.name, ', ' order by pl.id) as summary
      from public.purchase_order_lines pl join public.parts p on p.id = pl.part_id
     where pl.order_id = o.id
  ) l on true
"""


@router.get("/orders", summary="Satınalma talepleri ve siparişler")
def orders(
    ctx: TenantCtx,
    status: PoStatus | None = None,
    open_only: bool = Query(False, description="Yalnızca talep / sipariş / kısmi teslim"),
    supplier_id: UUID | None = None,
    q: str | None = Query(None, max_length=60),
    limit: int = Query(200, ge=1, le=500),
):
    with ctx.tx() as conn:
        return conn.execute(
            ORDER_LIST_SQL + """
             where o.tenant_id = %(t)s
               and (%(s)s::text is null or o.status::text = %(s)s)
               and (not %(o)s or o.status in ('draft', 'ordered', 'partial'))
               and (%(sup)s::uuid is null or o.supplier_id = %(sup)s)
               and (%(q)s::text is null or o.number ilike '%%' || %(q)s || '%%' or s.name ilike '%%' || %(q)s || '%%'
                    or l.summary ilike '%%' || %(q)s || '%%')
             order by (o.status in ('draft', 'ordered', 'partial')) desc, o.created_at desc
             limit %(lim)s""",
            {"t": ctx.tenant_id, "s": status, "o": open_only, "sup": supplier_id, "q": q, "lim": limit},
        ).fetchall()


def _order_detail(conn, order_id: UUID, tenant_id: UUID) -> dict:
    o = conn.execute(ORDER_LIST_SQL + " where o.id = %s and o.tenant_id = %s", [order_id, tenant_id]).fetchone()
    if not o:
        raise HTTPException(404, "Sipariş bulunamadı")
    o["lines"] = conn.execute(
        """select pl.id, pl.part_id, p.name, p.manufacturer, p.part_no, p.unit, pc.is_serialized, pc.code as category_code,
                  pl.qty, pl.received_qty, coalesce(pl.unit_cost, p.list_cost) as unit_cost, pl.asset_id, a.code as asset_code, pl.notes
             from public.purchase_order_lines pl
             join public.parts p on p.id = pl.part_id
             join public.part_categories pc on pc.id = p.category_id
             left join public.assets a on a.id = pl.asset_id
            where pl.order_id = %s order by pl.id""", [order_id]).fetchall()
    o["receipts"] = conn.execute(
        """select r.id, r.line_id, p.name, r.qty, r.ref, r.serials, r.received_at, s.name as site_name, u.full_name as received_by_name
             from public.purchase_receipts r
             join public.purchase_order_lines pl on pl.id = r.line_id
             join public.parts p on p.id = pl.part_id
             left join public.sites s on s.id = r.site_id
             left join public.app_users u on u.id = r.received_by
            where r.order_id = %s order by r.received_at desc, r.id desc""", [order_id]).fetchall()
    return o


def _check_refs(conn, ctx: TenantCtx, supplier_id: UUID | None, site_id: UUID | None, lines: list[LineIn] | None) -> None:
    if supplier_id and not conn.execute("select 1 from public.suppliers where id = %s and tenant_id = %s",
                                        [supplier_id, ctx.tenant_id]).fetchone():
        raise HTTPException(404, "Tedarikçi bulunamadı")
    if site_id and not conn.execute("select 1 from public.sites where id = %s and tenant_id = %s",
                                    [site_id, ctx.tenant_id]).fetchone():
        raise HTTPException(404, "Depo bulunamadı")
    for ln in lines or []:
        if not conn.execute("select 1 from public.parts where id = %s and (tenant_id = %s or tenant_id is null)",
                            [ln.part_id, ctx.tenant_id]).fetchone():
            raise HTTPException(404, "Katalog kalemi bulunamadı")
        if ln.asset_id and not conn.execute("select 1 from public.assets where id = %s and tenant_id = %s",
                                            [ln.asset_id, ctx.tenant_id]).fetchone():
            raise HTTPException(404, "Makine bulunamadı")


def _insert_lines(conn, ctx: TenantCtx, order_id: UUID, lines: list[LineIn]) -> None:
    for ln in lines:
        conn.execute(
            """insert into public.purchase_order_lines (tenant_id, order_id, part_id, qty, unit_cost, asset_id, notes)
               values (%s, %s, %s, %s, %s, %s, %s)""",
            [ctx.tenant_id, order_id, ln.part_id, ln.qty, ln.unit_cost, ln.asset_id, ln.notes])


@router.get("/orders/{order_id}", summary="Sipariş ayrıntısı: satırlar ve teslim alma kayıtları")
def order_get(order_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        return _order_detail(conn, order_id, ctx.tenant_id)


@router.post("/orders", status_code=201, summary="Satınalma talebi aç (talep durumunda başlar)")
def order_create(body: OrderIn, ctx: TenantCtx, request: Request):
    ctx.require("technician")
    with ctx.tx() as conn:
        _check_refs(conn, ctx, body.supplier_id, body.site_id, body.lines)
        row = conn.execute(
            """insert into public.purchase_orders (tenant_id, number, supplier_id, site_id, expected_at, notes, requested_by)
               values (%s, app.next_po_number(%s), %s, %s, %s, %s, %s) returning id, number""",
            [ctx.tenant_id, ctx.tenant_id, body.supplier_id, body.site_id, body.expected_at, body.notes, ctx.user_id],
        ).fetchone()
        _insert_lines(conn, ctx, row["id"], body.lines)
        request.state.audit = {"number": row["number"], "lines": len(body.lines)}
        return _order_detail(conn, row["id"], ctx.tenant_id)


@router.patch("/orders/{order_id}", summary="Talebi / siparişi düzenle")
def order_update(order_id: UUID, body: OrderPatch, ctx: TenantCtx, request: Request):
    ctx.require("technician")
    with ctx.tx() as conn:
        cur = conn.execute("select status, number from public.purchase_orders where id = %s and tenant_id = %s",
                           [order_id, ctx.tenant_id]).fetchone()
        if not cur:
            raise HTTPException(404, "Sipariş bulunamadı")
        if cur["status"] in ("received", "cancelled"):
            raise HTTPException(422, "Kapanmış sipariş düzenlenemez")
        if body.lines is not None and cur["status"] != "draft":
            raise HTTPException(422, "Sipariş verildikten sonra kalemler değiştirilemez; yeni talep açın")
        _check_refs(conn, ctx, body.supplier_id, body.site_id, body.lines)
        fields = body.model_dump(exclude_unset=True, exclude={"lines"})
        if fields:
            sets = ", ".join(f"{k} = %s" for k in fields)
            conn.execute(f"update public.purchase_orders set {sets} where id = %s", [*fields.values(), order_id])
        if body.lines is not None:
            conn.execute("delete from public.purchase_order_lines where order_id = %s", [order_id])
            _insert_lines(conn, ctx, order_id, body.lines)
        request.state.audit = {"number": cur["number"], "changed": sorted(fields) + (["lines"] if body.lines is not None else [])}
        return _order_detail(conn, order_id, ctx.tenant_id)


@router.post("/orders/{order_id}/status", summary="Sipariş ver, iptal et veya kısmi teslimatı kapat")
def order_status(order_id: UUID, body: StatusIn, ctx: TenantCtx, request: Request):
    ctx.require("manager")
    with ctx.tx() as conn:
        if not conn.execute("select 1 from public.purchase_orders where id = %s and tenant_id = %s",
                            [order_id, ctx.tenant_id]).fetchone():
            raise HTTPException(404, "Sipariş bulunamadı")
        row = conn.execute("select number, status from public.po_set_status(%s, %s)", [order_id, body.status]).fetchone()
        request.state.audit = {"number": row["number"], "status": row["status"]}
        return _order_detail(conn, order_id, ctx.tenant_id)


@router.post("/orders/{order_id}/receive", summary="Teslim al: sarf kalemi stoğa, seri numaralı parça kalem olarak girer")
def order_receive(order_id: UUID, body: ReceiveIn, ctx: TenantCtx, request: Request):
    ctx.require("technician")
    with ctx.tx() as conn:
        cur = conn.execute("select number from public.purchase_orders where id = %s and tenant_id = %s",
                           [order_id, ctx.tenant_id]).fetchone()
        if not cur:
            raise HTTPException(404, "Sipariş bulunamadı")
        if body.site_id and not conn.execute("select 1 from public.sites where id = %s and tenant_id = %s",
                                             [body.site_id, ctx.tenant_id]).fetchone():
            raise HTTPException(404, "Depo bulunamadı")
        line_ids = {r["id"] for r in conn.execute(
            "select id from public.purchase_order_lines where order_id = %s", [order_id]).fetchall()}
        received = []
        for ln in body.lines:
            if ln.line_id not in line_ids:
                raise HTTPException(404, "Sipariş kalemi bulunamadı")
            serials = [s.get("serial_no") for s in ln.serials or [] if s.get("serial_no")]
            if len(serials) != len(set(serials)):
                raise HTTPException(422, "Aynı seri numarası listede birden fazla kez var")
            r = conn.execute(
                "select id, line_id, qty, serials from public.po_receive(%s, %s, %s, %s, %s)",
                [ln.line_id, ln.qty, body.site_id, body.ref, Jsonb(ln.serials) if ln.serials is not None else None],
            ).fetchone()
            received.append({"line_id": r["line_id"], "qty": format(r["qty"].normalize(), "f")})
        request.state.audit = {"number": cur["number"], "ref": body.ref, "received": received}
        return _order_detail(conn, order_id, ctx.tenant_id)
