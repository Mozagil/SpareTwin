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


# ---------- Tedarikçi karşılaştırma ----------
# Ek veri girişi yok: verilmiş siparişler ve teslim alma kayıtlarından hesaplanır.
# Bir satır "teslim edildi" sayılır: sipariş edilen miktarın tamamı teslim alındıysa; teslim süresi
# sipariş tarihinden son teslimata kadardır. Eksik kapatılan satır süre ve zamanında oranına girmez.
COMPARE_LINES = """
with ln as (
  select pl.part_id, o.supplier_id, o.id as order_id, o.ordered_at, o.expected_at, o.status,
         pl.qty, pl.received_qty, coalesce(pl.unit_cost, p.list_cost) as unit_cost,
         (select max(r.received_at) from public.purchase_receipts r where r.line_id = pl.id) as last_receipt
    from public.purchase_order_lines pl
    join public.purchase_orders o on o.id = pl.order_id
    join public.parts p on p.id = pl.part_id
   where o.tenant_id = %(t)s and o.status in ('ordered', 'partial', 'received')
     and o.supplier_id is not null and o.ordered_at >= now() - make_interval(months => %(m)s)
     and (%(part)s::uuid is null or pl.part_id = %(part)s)
)
"""
COMPARE_AGG = """
  count(distinct order_id) as order_count,
  sum(qty * unit_cost) as spend,
  count(*) filter (where received_qty >= qty) as delivered,
  avg(extract(epoch from last_receipt - ordered_at) / 86400.0) filter (where received_qty >= qty) as avg_lead_days,
  count(*) filter (where received_qty >= qty and expected_at is not null) as timed,
  count(*) filter (where received_qty >= qty and expected_at is not null and last_receipt::date <= expected_at) as on_time,
  count(*) filter (where status = 'received' and received_qty < qty) as short
"""


def _best(rows: list[dict], key: str) -> None:
    """Değeri en düşük olan tek tedarikçiyi işaretler (ör. cheapest); eşitlik ya da tek veri varsa kimse işaretlenmez."""
    flag = {"avg_cost": "cheapest", "avg_lead_days": "fastest"}[key]
    vals = sorted((float(r[key]), i) for i, r in enumerate(rows) if r[key] is not None)
    for r in rows:
        r[flag] = False
    if len(vals) >= 2 and vals[0][0] < vals[1][0]:
        rows[vals[0][1]][flag] = True


@router.get("/supplier-comparison", summary="Tedarikçi karşılaştırma: kalem bazında kimden kaç kez, kaça, kaç günde alındı")
def supplier_comparison(
    ctx: TenantCtx,
    months: int = Query(12, ge=1, le=60, description="Geriye dönük dönem (sipariş tarihi)"),
    part_id: UUID | None = None,
):
    args = {"t": ctx.tenant_id, "m": months, "part": part_id}
    with ctx.tx() as conn:
        # Renk tedarikçiyi anlatır: sıra dönemden bağımsız ve sabit olsun diye tüm tedarikçiler döner
        suppliers = conn.execute(
            f"""{COMPARE_LINES}
                select s.id as supplier_id, s.name as supplier_name, s.is_active, s.lead_time_days,
                       coalesce(a.order_count, 0) as order_count, coalesce(a.spend, 0) as spend,
                       coalesce(a.part_count, 0) as part_count, coalesce(a.delivered, 0) as delivered, a.avg_lead_days,
                       coalesce(a.timed, 0) as timed, coalesce(a.on_time, 0) as on_time, coalesce(a.short, 0) as short
                  from public.suppliers s
                  left join (select supplier_id, count(distinct part_id) as part_count, {COMPARE_AGG}
                               from ln group by supplier_id) a on a.supplier_id = s.id
                 where s.tenant_id = %(t)s
                 order by s.created_at, s.id""",
            args,
        ).fetchall()
        rows = conn.execute(
            f"""{COMPARE_LINES}
                select ln.part_id, p.name, p.manufacturer, p.part_no, p.unit, pc.code as category_code,
                       ln.supplier_id, s.name as supplier_name, sum(ln.qty) as qty,
                       sum(ln.qty * ln.unit_cost) / nullif(sum(ln.qty) filter (where ln.unit_cost is not null), 0) as avg_cost,
                       (array_agg(ln.unit_cost order by ln.ordered_at desc))[1] as last_cost,
                       max(ln.ordered_at) as last_ordered_at, {COMPARE_AGG}
                  from ln
                  join public.parts p on p.id = ln.part_id
                  join public.part_categories pc on pc.id = p.category_id
                  join public.suppliers s on s.id = ln.supplier_id
                 group by ln.part_id, p.name, p.manufacturer, p.part_no, p.unit, pc.code, ln.supplier_id, s.name
                 order by p.name, ln.part_id, count(distinct ln.order_id) desc, s.name""",
            args,
        ).fetchall()
        period_from = conn.execute("select now() - make_interval(months => %s) as f", [months]).fetchone()["f"]

    parts: dict[UUID, dict] = {}
    for r in rows:
        part = parts.setdefault(r["part_id"], {
            "part_id": r["part_id"], "name": r["name"], "manufacturer": r["manufacturer"], "part_no": r["part_no"],
            "unit": r["unit"], "category_code": r["category_code"], "order_count": 0, "spend": 0, "suppliers": []})
        part["order_count"] += r["order_count"]
        part["spend"] += r["spend"] or 0
        part["suppliers"].append({k: r[k] for k in (
            "supplier_id", "supplier_name", "order_count", "qty", "spend", "avg_cost", "last_cost", "last_ordered_at",
            "delivered", "avg_lead_days", "timed", "on_time", "short")})
    for part in parts.values():
        _best(part["suppliers"], "avg_cost")
        _best(part["suppliers"], "avg_lead_days")
    # Karşılaştırılabilir kalemler (birden çok tedarikçi) önce, sonra harcamaya göre
    ordered = sorted(parts.values(), key=lambda p: (-len(p["suppliers"]), -float(p["spend"]), p["name"]))
    return {"months": months, "from": period_from, "suppliers": suppliers, "parts": ordered}
