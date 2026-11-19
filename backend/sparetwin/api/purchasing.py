"""Satınalma (Faz 2): tedarikçiler, öneriler, talep → sipariş → teslim alma.

Yetki: talep açma ve teslim alma teknisyen; siparişi verme ve iptal yönetici.
Teslim alma: sarf malzemesi stock_move ile stoğa (sipariş fiyatı, belge no),
seri numaralı parça part_items olarak (seri no ile) girer.
"""

import math
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .deps import Ctx, TenantCtx

router = APIRouter(tags=["Satınalma"])
DUE_HOURS = 1000  # satınalma ufku: bu kadar saat içinde değişecek lastikler (tedarik süresi için)


# ---------- Tedarikçiler ----------
class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=1000)


@router.get("/suppliers", summary="Tedarikçiler")
def suppliers(ctx: TenantCtx):
    with ctx.tx() as conn:
        return conn.execute(
            """select s.*, (select count(*) from public.purchase_orders po where po.supplier_id = s.id
                              and po.status <> 'cancelled') as orders
                 from public.suppliers s where s.tenant_id = %s order by s.active desc, s.name""",
            [ctx.tenant_id]).fetchall()


@router.post("/suppliers", status_code=201, summary="Tedarikçi ekle")
def create_supplier(body: SupplierIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        return conn.execute(
            """insert into public.suppliers (tenant_id, name, contact, phone, email, notes)
               values (%s, %s, %s, %s, %s, %s) returning *""",
            [ctx.tenant_id, body.name.strip(), body.contact, body.phone, body.email, body.notes]).fetchone()


# ---------- Öneriler ----------
@router.get("/purchasing/suggestions", summary="Ne almalıyım? Kritik seviye ve yaklaşan lastik değişimleri")
def suggestions(ctx: TenantCtx):
    from .settings import get_settings
    with ctx.tx() as conn:
        horizon = get_settings(conn, ctx.tenant_id)["purchase_horizon_hours"]
        stock = {r["part_id"]: r for r in conn.execute(
            """select st.part_id, st.name, st.unit, st.min_stock, st.qty, st.is_serialized, st.category_code,
                      st.avg_cost, coalesce(oo.qty, 0) as on_order
                 from public.v_stock_totals st
                 left join public.v_on_order oo on oo.part_id = st.part_id and oo.tenant_id = st.tenant_id
                where st.tenant_id = %s""", [ctx.tenant_id]).fetchall()}
        due = conn.execute(
            """select l.part_id, ph.asset_code, ph.current_position, ph.projected_hours_left
                 from public.v_part_health ph join public.v_part_items_live l on l.id = ph.id
                where ph.tenant_id = %s and ph.status = 'installed' and ph.category_code = 'tire'
                  and ph.projected_hours_left is not null and ph.projected_hours_left <= %s
                order by ph.projected_hours_left""", [ctx.tenant_id, horizon]).fetchall()
        last_supplier = {r["part_id"]: r for r in conn.execute(
            """select distinct on (l.part_id) l.part_id, po.supplier_id, s.name as supplier_name, l.unit_cost
                 from public.purchase_order_lines l join public.purchase_orders po on po.id = l.po_id
                 left join public.suppliers s on s.id = po.supplier_id
                where l.tenant_id = %s and po.status <> 'cancelled' and po.supplier_id is not null
                order by l.part_id, po.created_at desc""", [ctx.tenant_id]).fetchall()}

    due_by_part: dict[UUID, list] = {}
    for d in due:
        due_by_part.setdefault(d["part_id"], []).append(d)

    out = []
    for pid, s in stock.items():
        upcoming = due_by_part.get(pid, [])
        if not s["min_stock"] and not upcoming:
            continue
        # Değişimler yapıldıktan sonra stok yine kritik seviyenin üstünde kalmalı
        need = Decimal(s["min_stock"]) + len(upcoming) - Decimal(s["qty"]) - Decimal(s["on_order"])
        if need <= 0:
            continue
        reasons = [f"Stokta {_q(s['qty'])} {s['unit']}, kritik seviye {s['min_stock']}"]
        if s["on_order"]:
            reasons.append(f"Yolda {_q(s['on_order'])} {s['unit']}")
        if upcoming:
            reasons.append(f"{horizon:,} saat içinde {len(upcoming)} değişim: ".replace(",", ".")
                           + ", ".join(f"{u['asset_code']} {u['current_position']} (~{int(u['projected_hours_left'])} sa)" for u in upcoming[:4])
                           + ("…" if len(upcoming) > 4 else ""))
        ls = last_supplier.get(pid)
        out.append({
            "part_id": pid, "name": s["name"], "unit": s["unit"], "category_code": s["category_code"],
            "is_serialized": s["is_serialized"],
            "suggested_qty": math.ceil(need) if s["is_serialized"] or s["unit"] in ("adet", "takım") else need,
            "qty": s["qty"], "min_stock": s["min_stock"], "on_order": s["on_order"], "upcoming": len(upcoming),
            "reasons": reasons, "unit_cost": (ls or {}).get("unit_cost") or s["avg_cost"],
            "supplier_id": (ls or {}).get("supplier_id"), "supplier_name": (ls or {}).get("supplier_name"),
            "urgent": bool(upcoming) or Decimal(s["qty"]) < Decimal(s["min_stock"]),
        })
    out.sort(key=lambda x: (not x["upcoming"], x["name"]))
    return out


def _q(v) -> str:
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:.1f}".replace(".", ",")


# ---------- Belgeler ----------
class LineIn(BaseModel):
    part_id: UUID
    qty: Decimal = Field(gt=0, le=1_000_000)
    unit_cost: Decimal | None = Field(None, ge=0)
    note: str | None = Field(None, max_length=300)


class OrderIn(BaseModel):
    supplier_id: UUID | None = None
    expected_date: date | None = None
    notes: str | None = Field(None, max_length=2000)
    lines: list[LineIn] = Field(min_length=1, max_length=200)


class OrderPatch(BaseModel):
    supplier_id: UUID | None = None
    expected_date: date | None = None
    notes: str | None = Field(None, max_length=2000)


class LinePatch(BaseModel):
    qty: Decimal | None = Field(None, gt=0, le=1_000_000)
    unit_cost: Decimal | None = Field(None, ge=0)


class ReceiveLine(BaseModel):
    line_id: UUID
    qty: Decimal = Field(gt=0)
    serials: list[str] = Field(default_factory=list, max_length=500)


class ReceiveIn(BaseModel):
    site_id: UUID | None = None
    ref: str | None = Field(None, max_length=60, description="İrsaliye / fatura no")
    lines: list[ReceiveLine] = Field(min_length=1)


STATUS_TR = {"draft": "Talep", "ordered": "Sipariş verildi", "partial": "Kısmen teslim alındı",
             "received": "Teslim alındı", "cancelled": "İptal edildi"}


def _po(conn, po_id: UUID, tenant_id: UUID, lock: bool = False) -> dict:
    row = conn.execute(
        f"""select po.*, s.name as supplier_name from public.purchase_orders po
              left join public.suppliers s on s.id = po.supplier_id
             where po.id = %s and po.tenant_id = %s {'for update of po' if lock else ''}""",
        [po_id, tenant_id]).fetchone()
    if not row:
        raise HTTPException(404, "Satınalma belgesi bulunamadı")
    return row


def _require_status(po: dict, *allowed: str) -> None:
    if po["status"] not in allowed:
        raise HTTPException(409, f"{po['number']} şu an '{STATUS_TR[po['status']]}' durumunda; bu işlem yapılamaz")


def _check_supplier(conn, supplier_id: UUID | None, tenant_id: UUID) -> None:
    if supplier_id and not conn.execute(
            "select 1 from public.suppliers where id = %s and tenant_id = %s", [supplier_id, tenant_id]).fetchone():
        raise HTTPException(404, "Tedarikçi bulunamadı")


def _add_lines(conn, ctx: Ctx, po_id: UUID, lines: list[LineIn]) -> None:
    for ln in lines:
        part = conn.execute(
            """select p.id, p.list_cost, pc.is_serialized from public.parts p join public.part_categories pc on pc.id = p.category_id
                where p.id = %s and (p.tenant_id = %s or p.tenant_id is null)""", [ln.part_id, ctx.tenant_id]).fetchone()
        if not part:
            raise HTTPException(404, "Katalog kalemi bulunamadı")
        if part["is_serialized"] and ln.qty != ln.qty.to_integral_value():
            raise HTTPException(422, "Seri numaralı parçalar tam sayı adetle sipariş edilir")
        conn.execute(
            """insert into public.purchase_order_lines (tenant_id, po_id, part_id, qty, unit_cost, note)
               values (%s, %s, %s, %s, %s, %s)""",
            [ctx.tenant_id, po_id, ln.part_id, ln.qty, ln.unit_cost if ln.unit_cost is not None else part["list_cost"], ln.note])


@router.get("/purchase-orders", summary="Satınalma belgeleri")
def list_orders(ctx: TenantCtx, status: str | None = None):
    with ctx.tx() as conn:
        return conn.execute(
            """select po.id, po.number, po.status, po.expected_date, po.created_at, po.ordered_at, po.received_at,
                      s.name as supplier_name, count(l.id) as lines,
                      coalesce(sum(l.qty * coalesce(l.unit_cost, 0)), 0) as total,
                      po.status in ('ordered', 'partial') and po.expected_date < current_date as late
                 from public.purchase_orders po
                 left join public.suppliers s on s.id = po.supplier_id
                 left join public.purchase_order_lines l on l.po_id = po.id
                where po.tenant_id = %s and (%s::text is null or po.status::text = %s)
                group by po.id, s.name
                order by case po.status when 'draft' then 0 when 'ordered' then 1 when 'partial' then 1 else 2 end,
                         po.created_at desc""",
            [ctx.tenant_id, status, status]).fetchall()


@router.get("/purchase-orders/{po_id}", summary="Satınalma belgesi ve satırları")
def get_order(po_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        po = _po(conn, po_id, ctx.tenant_id)
        po["lines"] = conn.execute(
            """select l.*, p.name as part_name, p.unit, p.part_no, pc.code as category_code, pc.is_serialized,
                      l.qty - l.received_qty as remaining
                 from public.purchase_order_lines l join public.parts p on p.id = l.part_id
                 join public.part_categories pc on pc.id = p.category_id
                where l.po_id = %s order by p.name""", [po_id]).fetchall()
        po["total"] = sum((l["qty"] * (l["unit_cost"] or 0) for l in po["lines"]), Decimal(0))
        po["late"] = po["status"] in ("ordered", "partial") and po["expected_date"] is not None and po["expected_date"] < date.today()
        return po


@router.post("/purchase-orders", status_code=201, summary="Talep oluştur (taslak)")
def create_order(body: OrderIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _check_supplier(conn, body.supplier_id, ctx.tenant_id)
        number = conn.execute("select app.next_po_number(%s) as n", [ctx.tenant_id]).fetchone()["n"]
        po = conn.execute(
            """insert into public.purchase_orders (tenant_id, number, supplier_id, expected_date, notes, created_by)
               values (%s, %s, %s, %s, %s, %s) returning id, number, status""",
            [ctx.tenant_id, number, body.supplier_id, body.expected_date, body.notes, ctx.user_id]).fetchone()
        _add_lines(conn, ctx, po["id"], body.lines)
        return po


@router.patch("/purchase-orders/{po_id}", summary="Tedarikçi, beklenen tarih, not")
def patch_order(po_id: UUID, body: OrderPatch, ctx: TenantCtx):
    ctx.require("technician")
    fields = body.model_dump(exclude_unset=True)
    with ctx.tx() as conn:
        po = _po(conn, po_id, ctx.tenant_id, lock=True)
        _require_status(po, "draft", "ordered", "partial")
        if "supplier_id" in fields:
            _require_status(po, "draft")
            _check_supplier(conn, fields["supplier_id"], ctx.tenant_id)
        if fields:
            sets = ", ".join(f"{k} = %({k})s" for k in fields)  # anahtarlar modelden
            conn.execute(f"update public.purchase_orders set {sets} where id = %(id)s", {**fields, "id": po_id})
        return {"id": po_id}


@router.post("/purchase-orders/{po_id}/lines", status_code=201, summary="Taslağa satır ekle")
def add_line(po_id: UUID, body: LineIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _require_status(_po(conn, po_id, ctx.tenant_id, lock=True), "draft")
        _add_lines(conn, ctx, po_id, [body])
        return {"id": po_id}


@router.patch("/purchase-orders/{po_id}/lines/{line_id}", summary="Taslak satırını değiştir")
def patch_line(po_id: UUID, line_id: UUID, body: LinePatch, ctx: TenantCtx):
    ctx.require("technician")
    fields = body.model_dump(exclude_unset=True)
    with ctx.tx() as conn:
        _require_status(_po(conn, po_id, ctx.tenant_id, lock=True), "draft")
        if fields:
            sets = ", ".join(f"{k} = %({k})s" for k in fields)
            r = conn.execute(f"update public.purchase_order_lines set {sets} where id = %(l)s and po_id = %(p)s",
                             {**fields, "l": line_id, "p": po_id})
            if r.rowcount == 0:
                raise HTTPException(404, "Satır bulunamadı")
        return {"id": line_id}


@router.delete("/purchase-orders/{po_id}/lines/{line_id}", status_code=204, summary="Taslaktan satır sil")
def delete_line(po_id: UUID, line_id: UUID, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _require_status(_po(conn, po_id, ctx.tenant_id, lock=True), "draft")
        if conn.execute("delete from public.purchase_order_lines where id = %s and po_id = %s", [line_id, po_id]).rowcount == 0:
            raise HTTPException(404, "Satır bulunamadı")


class PlaceIn(BaseModel):
    expected_date: date | None = None


@router.post("/purchase-orders/{po_id}/order", summary="Siparişi ver (yönetici)")
def place(po_id: UUID, body: PlaceIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        po = _po(conn, po_id, ctx.tenant_id, lock=True)
        _require_status(po, "draft")
        if not po["supplier_id"]:
            raise HTTPException(422, "Sipariş vermek için tedarikçi seçin")
        if not conn.execute("select 1 from public.purchase_order_lines where po_id = %s", [po_id]).fetchone():
            raise HTTPException(422, "Belgede satır yok")
        conn.execute(
            """update public.purchase_orders set status = 'ordered', ordered_by = %s, ordered_at = now(),
                      expected_date = coalesce(%s, expected_date) where id = %s""",
            [ctx.user_id, body.expected_date, po_id])
        return {"id": po_id, "status": "ordered"}


@router.post("/purchase-orders/{po_id}/cancel", summary="İptal et (yönetici; teslim alınmış satır yoksa)")
def cancel(po_id: UUID, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        po = _po(conn, po_id, ctx.tenant_id, lock=True)
        _require_status(po, "draft", "ordered")
        if conn.execute("select 1 from public.purchase_order_lines where po_id = %s and received_qty > 0", [po_id]).fetchone():
            raise HTTPException(409, "Teslim alınmış satır var; iptal edilemez")
        conn.execute("update public.purchase_orders set status = 'cancelled' where id = %s", [po_id])
        return {"id": po_id, "status": "cancelled"}


@router.post("/purchase-orders/{po_id}/receive", summary="Teslim al (kısmi olabilir): stoğa girer")
def receive(po_id: UUID, body: ReceiveIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        po = _po(conn, po_id, ctx.tenant_id, lock=True)
        _require_status(po, "ordered", "partial")
        if body.site_id and not conn.execute(
                "select 1 from public.sites where id = %s and tenant_id = %s", [body.site_id, ctx.tenant_id]).fetchone():
            raise HTTPException(404, "Depo bulunamadı")
        ref = body.ref or po["number"]
        created: list[str] = []
        for rl in body.lines:
            ln = conn.execute(
                """select l.*, p.name, pc.is_serialized from public.purchase_order_lines l
                     join public.parts p on p.id = l.part_id join public.part_categories pc on pc.id = p.category_id
                    where l.id = %s and l.po_id = %s for update of l""", [rl.line_id, po_id]).fetchone()
            if not ln:
                raise HTTPException(404, "Satır bulunamadı")
            remaining = ln["qty"] - ln["received_qty"]
            if rl.qty > remaining:
                raise HTTPException(422, f"{ln['name']}: en fazla {_q(remaining)} teslim alınabilir")
            if ln["is_serialized"]:
                if rl.qty != rl.qty.to_integral_value():
                    raise HTTPException(422, f"{ln['name']}: tam sayı adet girin")
                serials = [s.strip() for s in rl.serials if s.strip()]
                if serials and len(serials) != int(rl.qty):
                    raise HTTPException(422, f"{ln['name']}: {int(rl.qty)} adet için {int(rl.qty)} seri no girin (girilen {len(serials)})")
                if len(set(s.lower() for s in serials)) != len(serials):
                    raise HTTPException(422, f"{ln['name']}: aynı seri no birden fazla kez yazılmış")
                for i in range(int(rl.qty)):
                    item = conn.execute(
                        """insert into public.part_items (tenant_id, part_id, serial_no, qr_code, status, site_id, purchase_cost, acquired_at)
                           values (%s, %s, %s, app.new_qr('ST-P-'), 'in_stock', %s, %s, current_date) returning id""",
                        [ctx.tenant_id, ln["part_id"], serials[i] if serials else None, body.site_id, ln["unit_cost"]]).fetchone()["id"]
                    conn.execute(
                        """insert into public.part_events (tenant_id, part_item_id, event_type, part_hours, notes, performed_by)
                           values (%s, %s, 'received', 0, %s, %s)""",
                        [ctx.tenant_id, item, f"{po['number']} ile teslim alındı · {ref}", ctx.user_id])
                    created.append(str(item))
            else:
                conn.execute("select 1 from public.stock_move(%s, %s, 'in', %s, %s, null, 'satınalma', %s, %s, null, %s)",
                             [ln["part_id"], body.site_id, rl.qty, ln["unit_cost"], ref, po["number"], ctx.tenant_id])
            conn.execute("update public.purchase_order_lines set received_qty = received_qty + %s where id = %s", [rl.qty, ln["id"]])
        done = not conn.execute(
            "select 1 from public.purchase_order_lines where po_id = %s and received_qty < qty", [po_id]).fetchone()
        status: Literal["received", "partial"] = "received" if done else "partial"
        conn.execute("update public.purchase_orders set status = %s, received_at = case when %s then now() end where id = %s",
                     [status, done, po_id])
        return {"id": po_id, "status": status, "part_ids": created}
