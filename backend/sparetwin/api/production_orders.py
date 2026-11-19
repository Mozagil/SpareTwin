"""Üretim emri, rota, işlem süresi, fire, hurda ve üretim maliyeti.

Rota: ürün ağacının sıralı işlemleri ve 1 birim için planlanan süre. Emir açılınca işlemler
ve ürün ağacının birinci seviye bileşenleri emre kopyalanır (plan = birim × miktar); işlem
başında başla / durdur ile süre tutulur. Emir tamamlanırken gerçekleşen malzeme kullanımı
stoktan düşer, sağlam ürün stoğa girer; plandan fazlası fire, kullanılamayan ürün hurdadır.
Yetki: rota, emir açma ve iptal yönetici (manager) ve üstü; başla / durdur / bitir ve emri
tamamlama teknisyen ve üstü. Kurallar veritabanında (0021, 0022, 0023).

Maliyet = malzeme + işçilik + makine saati. Emir tamamlanırken hesaplanır ve emre yazılır
(prod_complete); açık emirde yalnızca plan gösterilir. İşçilik oranı firma ayarıdır
(labor_cost_per_hour), makine oranı rotada işleme yazılır.
"""

import json

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from ..tenant_settings import thresholds
from .deps import TenantCtx

router = APIRouter(prefix="/production", tags=["Üretim"])

ProdStatus = Literal["open", "in_progress", "done", "cancelled"]
ScrapReason = Literal["material", "workmanship", "machine", "setup", "dimension", "damage", "other"]


# ---------- Rota ----------
class OperationIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    planned_minutes: Decimal | None = Field(None, gt=0, le=100_000, description="1 birim ürün için; boş = bilinmiyor")
    machine_rate: Decimal | None = Field(None, ge=0, le=100_000, description="Makine saat maliyeti; boş = bu işlemde makine maliyeti yok")


class RouteIn(BaseModel):
    operations: list[OperationIn] = Field(max_length=50, description="Sırasıyla işlemler; liste rotanın tamamını değiştirir")

    @model_validator(mode="after")
    def _unique(self):
        names = [o.name.strip().lower() for o in self.operations]
        if len(names) != len(set(names)):
            raise ValueError("Aynı işlem rotada birden fazla kez var")
        return self


def _bom(conn, bom_id: UUID, tenant_id: UUID) -> None:
    if not conn.execute("select 1 from public.boms where id = %s and tenant_id = %s", [bom_id, tenant_id]).fetchone():
        raise HTTPException(404, "Ürün ağacı bulunamadı")


def _route(conn, bom_id: UUID) -> list[dict]:
    return conn.execute("select id, seq, name, planned_minutes, machine_rate from public.bom_operations where bom_id = %s order by seq",
                        [bom_id]).fetchall()


@router.get("/routes/{bom_id}", summary="Rota: ürün ağacının sıralı işlemleri")
def route_get(bom_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        _bom(conn, bom_id, ctx.tenant_id)
        return _route(conn, bom_id)


@router.put("/routes/{bom_id}", summary="Rotayı kaydet (liste tümden değişir; açılmış emirler etkilenmez)")
def route_put(bom_id: UUID, body: RouteIn, ctx: TenantCtx, request: Request):
    ctx.require("manager")
    with ctx.tx() as conn:
        _bom(conn, bom_id, ctx.tenant_id)
        conn.execute("delete from public.bom_operations where bom_id = %s", [bom_id])
        for i, o in enumerate(body.operations, 1):
            conn.execute(
                """insert into public.bom_operations (tenant_id, bom_id, seq, name, planned_minutes, machine_rate)
                   values (%s, %s, %s, %s, %s, %s)""",
                [ctx.tenant_id, bom_id, i, o.name.strip(), o.planned_minutes, o.machine_rate])
        request.state.audit = {"operations": len(body.operations)}
        return _route(conn, bom_id)


# ---------- Üretim emri ----------
class OrderIn(BaseModel):
    part_id: UUID = Field(description="Üretilecek kalem; ürün ağacı ve rotası olmalı")
    qty: Decimal = Field(gt=0, le=1_000_000)
    due_at: date | None = None
    notes: str | None = Field(None, max_length=1000)


class StopIn(BaseModel):
    done: bool = Field(False, description="true: işlem bitti (süren bütün kayıtlar kapanır)")


class StatusIn(BaseModel):
    status: Literal["cancelled"]


class MaterialUse(BaseModel):
    part_id: UUID
    actual_qty: Decimal = Field(ge=0, le=100_000_000)
    reason: ScrapReason | None = Field(None, description="Plandan fazla kullanımda zorunlu")


class FinishIn(BaseModel):
    site_id: UUID | None = Field(None, description="Malzemenin çıktığı, ürünün girdiği depo")
    good_qty: Decimal = Field(ge=0, le=1_000_000, description="Sağlam ürün")
    scrap_qty: Decimal = Field(Decimal(0), ge=0, le=1_000_000, description="Hurda ürün")
    scrap_reason: ScrapReason | None = None
    materials: list[MaterialUse] = Field(default_factory=list, max_length=500,
                                         description="Listede olmayan malzeme planlandığı kadar kullanılmış sayılır")


ORDER_SQL = """
select o.id, o.number, o.part_id, p.name, p.part_no, p.unit, o.qty, o.status, o.due_at, o.notes,
       o.started_at, o.completed_at, o.created_at, cu.full_name as created_by_name,
       o.good_qty, o.scrap_qty, o.scrap_reason, o.site_id, s.name as site_name,
       o.labor_rate, o.material_cost, o.labor_cost, o.machine_cost,
       o.material_cost + o.labor_cost + o.machine_cost as total_cost,
       round((o.material_cost + o.labor_cost + o.machine_cost) / nullif(o.good_qty, 0), 2) as unit_cost,
       (o.status in ('open', 'in_progress') and coalesce(o.due_at < current_date, false)) as late,
       x.op_count, x.ops_done, x.planned_minutes, x.actual_minutes, x.running
  from public.production_orders o
  join public.parts p on p.id = o.part_id
  left join public.app_users cu on cu.id = o.created_by
  left join public.sites s on s.id = o.site_id
  left join lateral (
    select count(*) as op_count, count(v.done_at) as ops_done, sum(v.planned_minutes) as planned_minutes,
           coalesce(sum(v.actual_minutes), 0) as actual_minutes, coalesce(sum(v.running), 0) as running
      from public.v_production_ops v where v.order_id = o.id
  ) x on true
"""


def _order(conn, order_id: UUID, ctx: TenantCtx) -> dict:
    o = conn.execute(ORDER_SQL + " where o.id = %s and o.tenant_id = %s", [order_id, ctx.tenant_id]).fetchone()
    if not o:
        raise HTTPException(404, "Üretim emri bulunamadı")
    o["operations"] = conn.execute(
        """select v.id, v.seq, v.name, v.planned_minutes, v.actual_minutes, v.machine_rate, v.done_at, du.full_name as done_by_name,
                  coalesce(w.workers, '{}') as running_by,
                  exists (select 1 from public.production_time_logs l
                           where l.op_id = v.id and l.ended_at is null and l.user_id = %s) as mine
             from public.v_production_ops v
             left join public.app_users du on du.id = v.done_by
             left join lateral (
               select array_agg(u.full_name order by l.started_at) as workers
                 from public.production_time_logs l join public.app_users u on u.id = l.user_id
                where l.op_id = v.id and l.ended_at is null
             ) w on true
            where v.order_id = %s order by v.seq""", [ctx.user_id, order_id]).fetchall()
    o["logs"] = conn.execute(
        """select l.id, x.name as operation, u.full_name as user_name, l.started_at, l.ended_at,
                  round((extract(epoch from (coalesce(l.ended_at, now()) - l.started_at)) / 60)::numeric, 1) as minutes
             from public.production_time_logs l
             join public.production_order_ops x on x.id = l.op_id
             join public.app_users u on u.id = l.user_id
            where x.order_id = %s order by l.started_at desc""", [order_id]).fetchall()
    o["materials"] = conn.execute(
        """select m.part_id, p.name, p.part_no, p.unit, pc.is_serialized, m.planned_qty, m.actual_qty, m.reason,
                  m.unit_cost, m.stock_moved, coalesce(st.qty, 0) as in_stock, coalesce(st.sites, '[]') as stock_sites,
                  st.avg_cost
             from public.production_order_materials m
             join public.parts p on p.id = m.part_id
             join public.part_categories pc on pc.id = p.category_id
             left join public.v_stock_totals st on st.part_id = m.part_id and st.tenant_id = m.tenant_id
            where m.order_id = %s order by m.id""", [order_id]).fetchall()
    o["planned_cost"] = _planned_cost(conn, o, ctx)
    return o


def _planned_cost(conn, o: dict, ctx: TenantCtx) -> dict:
    """Plana göre maliyet: planlanan malzeme ve süre, emrin oranlarıyla.

    Tamamlanmış emirde tüketim anındaki birim maliyet ve o günkü işçilik oranı kullanılır
    (gerçekleşenle aynı fiyat: fark yalnızca miktar ve süreden gelir); açık emirde stok
    ortalama maliyeti ve bugünkü oran.
    """
    rate = o["labor_rate"] if o["labor_rate"] is not None else Decimal(str(thresholds(conn, ctx.tenant_id)["labor_cost_per_hour"]))
    material = sum((m["planned_qty"] * (m["unit_cost"] if m["unit_cost"] is not None else m["avg_cost"] or 0)
                    for m in o["materials"]), Decimal(0))
    hours = [((op["planned_minutes"] or 0) / Decimal(60), op["machine_rate"] or 0) for op in o["operations"]]
    labor = sum((h for h, _ in hours), Decimal(0)) * rate
    machine = sum((h * r for h, r in hours), Decimal(0))
    q = Decimal("0.01")
    out = {"labor_rate": rate, "material": material.quantize(q), "labor": labor.quantize(q), "machine": machine.quantize(q)}
    out["total"] = out["material"] + out["labor"] + out["machine"]
    out["unit"] = (out["total"] / o["qty"]).quantize(q)
    return out


def _op(conn, order_id: UUID, op_id: UUID, tenant_id: UUID) -> None:
    if not conn.execute("select 1 from public.production_order_ops where id = %s and order_id = %s and tenant_id = %s",
                        [op_id, order_id, tenant_id]).fetchone():
        raise HTTPException(404, "İşlem bulunamadı")


@router.get("/orders", summary="Üretim emirleri: ilerleme, planlanan ve gerçekleşen süre")
def orders(ctx: TenantCtx, status: ProdStatus | None = None,
           open_only: bool = Query(False, description="Yalnızca açık ve süren emirler"),
           limit: int = Query(200, ge=1, le=500)):
    with ctx.tx() as conn:
        return conn.execute(
            ORDER_SQL + """
             where o.tenant_id = %(t)s and (%(s)s::text is null or o.status::text = %(s)s)
               and (not %(o)s or o.status in ('open', 'in_progress'))
             order by (o.status in ('open', 'in_progress')) desc, coalesce(o.due_at, current_date + 3650), o.created_at desc
             limit %(lim)s""", {"t": ctx.tenant_id, "s": status, "o": open_only, "lim": limit}).fetchall()


@router.post("/orders", status_code=201, summary="Üretim emri aç (işlemler rotadan kopyalanır)")
def order_create(body: OrderIn, ctx: TenantCtx, request: Request):
    ctx.require("manager")
    with ctx.tx() as conn:
        bom = conn.execute("select id from public.boms where part_id = %s and tenant_id = %s", [body.part_id, ctx.tenant_id]).fetchone()
        if not bom:
            raise HTTPException(404, "Bu kalemin ürün ağacı yok")
        route = _route(conn, bom["id"])
        if not route:
            raise HTTPException(422, "Bu ürünün rotası boş; önce ürün ağacında işlemleri tanımlayın")
        row = conn.execute(
            """insert into public.production_orders (tenant_id, number, part_id, qty, due_at, notes, created_by)
               values (%s, app.next_prod_number(%s), %s, %s, %s, %s, %s) returning id, number""",
            [ctx.tenant_id, ctx.tenant_id, body.part_id, body.qty, body.due_at, body.notes, ctx.user_id]).fetchone()
        for r in route:
            conn.execute(
                """insert into public.production_order_ops (tenant_id, order_id, seq, name, planned_minutes, machine_rate)
                   values (%s, %s, %s, %s, %s, %s)""",
                [ctx.tenant_id, row["id"], r["seq"], r["name"],
                 r["planned_minutes"] * body.qty if r["planned_minutes"] is not None else None, r["machine_rate"]])
        conn.execute(
            """insert into public.production_order_materials (tenant_id, order_id, part_id, planned_qty)
               select %s, %s, l.part_id, l.qty * %s from public.bom_lines l where l.bom_id = %s order by l.id""",
            [ctx.tenant_id, row["id"], body.qty, bom["id"]])
        request.state.audit = {"number": row["number"], "qty": format(body.qty.normalize(), "f")}
        return _order(conn, row["id"], ctx)


@router.get("/orders/{order_id}", summary="Üretim emri: işlemler, süren işler, zaman kayıtları")
def order_get(order_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        return _order(conn, order_id, ctx)


@router.post("/orders/{order_id}/ops/{op_id}/start", summary="İşlemde çalışmaya başla (süre kaydı açılır)")
def op_start(order_id: UUID, op_id: UUID, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _op(conn, order_id, op_id, ctx.tenant_id)
        conn.execute("select id from public.prod_op_start(%s)", [op_id])
        return _order(conn, order_id, ctx)


@router.post("/orders/{order_id}/ops/{op_id}/stop", summary="Durdur ya da işlemi bitir")
def op_stop(order_id: UUID, op_id: UUID, body: StopIn, ctx: TenantCtx, request: Request):
    ctx.require("technician")
    with ctx.tx() as conn:
        _op(conn, order_id, op_id, ctx.tenant_id)
        op = conn.execute("select name from public.prod_op_stop(%s, %s)", [op_id, body.done]).fetchone()
        request.state.audit = {"operation": op["name"], "done": body.done}
        return _order(conn, order_id, ctx)


def _exists(conn, order_id: UUID, tenant_id: UUID) -> None:
    if not conn.execute("select 1 from public.production_orders where id = %s and tenant_id = %s",
                        [order_id, tenant_id]).fetchone():
        raise HTTPException(404, "Üretim emri bulunamadı")


@router.post("/orders/{order_id}/finish",
             summary="Emri tamamla: malzeme stoktan düşer, sağlam ürün stoğa girer, fire ve hurda kaydedilir")
def order_finish(order_id: UUID, body: FinishIn, ctx: TenantCtx, request: Request):
    ctx.require("technician")
    with ctx.tx() as conn:
        _exists(conn, order_id, ctx.tenant_id)
        mats = json.dumps([{"part_id": str(m.part_id), "actual_qty": str(m.actual_qty), "reason": m.reason}
                           for m in body.materials])
        row = conn.execute("select number from public.prod_complete(%s, %s, %s, %s, %s, %s::jsonb)",
                           [order_id, body.site_id, body.good_qty, body.scrap_qty, body.scrap_reason, mats]).fetchone()
        request.state.audit = {"number": row["number"], "good": format(body.good_qty.normalize(), "f"),
                               "scrap": format(body.scrap_qty.normalize(), "f")}
        return _order(conn, order_id, ctx)


@router.post("/orders/{order_id}/status", summary="Emri iptal et")
def order_status(order_id: UUID, body: StatusIn, ctx: TenantCtx, request: Request):
    ctx.require("manager")
    with ctx.tx() as conn:
        _exists(conn, order_id, ctx.tenant_id)
        row = conn.execute("select number, status from public.prod_set_status(%s, %s)", [order_id, body.status]).fetchone()
        request.state.audit = {"number": row["number"], "status": row["status"]}
        return _order(conn, order_id, ctx)


# ---------- İşlem raporu ----------
@router.get("/reports/operations", summary="İşlem bazında planlanan ve gerçekleşen süre (biten işlemler)")
def operations_report(ctx: TenantCtx, months: int = Query(12, ge=1, le=60)):
    with ctx.tx() as conn:
        return conn.execute(
            """select v.name, count(*) as op_count, count(distinct v.order_id) as order_count,
                      sum(v.planned_minutes) as planned_minutes, sum(v.actual_minutes) as actual_minutes,
                      -- Sapma yalnızca planı olan işlemlerden hesaplanır
                      coalesce(sum(v.actual_minutes) filter (where v.planned_minutes is not null), 0) as actual_planned_minutes
                 from public.v_production_ops v
                 join public.production_orders o on o.id = v.order_id
                where v.tenant_id = %s and o.status <> 'cancelled'
                  and v.done_at >= now() - make_interval(months => %s)
                group by v.name order by sum(v.actual_minutes) desc, v.name""", [ctx.tenant_id, months]).fetchall()


# ---------- Fire ve hurda raporu ----------
@router.get("/reports/scrap", summary="Fire ve hurda: ürün bazında hurda, malzeme bazında plan / gerçekleşen, sebep dağılımı")
def scrap_report(ctx: TenantCtx, months: int = Query(12, ge=1, le=60)):
    q = {"t": ctx.tenant_id, "m": months}
    done = "o.tenant_id = %(t)s and o.status = 'done' and o.good_qty is not null and o.completed_at >= now() - make_interval(months => %(m)s)"
    with ctx.tx() as conn:
        products = conn.execute(
            f"""select o.part_id, p.name, p.part_no, p.unit, count(*) as order_count, sum(o.qty) as planned_qty,
                       sum(o.good_qty) as good_qty, sum(o.scrap_qty) as scrap_qty
                  from public.production_orders o join public.parts p on p.id = o.part_id
                 where {done}
                 group by o.part_id, p.name, p.part_no, p.unit
                 order by sum(o.scrap_qty) / nullif(sum(o.good_qty + o.scrap_qty), 0) desc nulls last, p.name""", q).fetchall()
        materials = conn.execute(
            f"""select m.part_id, p.name, p.part_no, p.unit, count(*) as order_count, sum(m.planned_qty) as planned_qty,
                       sum(m.actual_qty) as actual_qty,
                       -- Fire tutarı: plandan sapma × tüketim anındaki birim maliyet; maliyeti bilinmeyen satır sayılmaz
                       sum((m.actual_qty - m.planned_qty) * m.unit_cost) as waste_cost
                  from public.production_order_materials m
                  join public.production_orders o on o.id = m.order_id
                  join public.parts p on p.id = m.part_id
                 where {done} and m.actual_qty is not null
                 group by m.part_id, p.name, p.part_no, p.unit
                 order by sum((m.actual_qty - m.planned_qty) * m.unit_cost) desc nulls last,
                          sum(m.actual_qty - m.planned_qty) desc, p.name""", q).fetchall()
        reasons = conn.execute(
            f"""select x.reason, sum(x.scrap) as scrap_orders, sum(x.waste) as waste_lines, sum(x.cost) as waste_cost
                  from (
                    select o.scrap_reason as reason, 1 as scrap, 0 as waste, null::numeric as cost
                      from public.production_orders o where {done} and o.scrap_qty > 0
                    union all
                    select m.reason, 0, 1, (m.actual_qty - m.planned_qty) * m.unit_cost
                      from public.production_order_materials m join public.production_orders o on o.id = m.order_id
                     where {done} and m.reason is not null
                  ) x
                 group by x.reason order by sum(x.scrap) + sum(x.waste) desc, x.reason""", q).fetchall()
        return {"months": months, "products": products, "materials": materials, "reasons": reasons}


# ---------- Üretim maliyeti raporu ----------
@router.get("/reports/cost", summary="Üretim maliyeti: ürün bazında malzeme, işçilik, makine ve birim maliyet (tamamlanan emirler)")
def cost_report(ctx: TenantCtx, months: int = Query(12, ge=1, le=60)):
    with ctx.tx() as conn:
        products = conn.execute(
            """select o.part_id, p.name, p.part_no, p.unit, count(*) as order_count,
                      sum(o.good_qty) as good_qty, sum(o.scrap_qty) as scrap_qty,
                      sum(o.material_cost) as material_cost, sum(o.labor_cost) as labor_cost, sum(o.machine_cost) as machine_cost,
                      sum(o.material_cost + o.labor_cost + o.machine_cost) as total_cost,
                      -- Birim maliyet: toplam / sağlam ürün (hurdanın maliyeti sağlam ürüne biner)
                      round(sum(o.material_cost + o.labor_cost + o.machine_cost) / nullif(sum(o.good_qty), 0), 2) as unit_cost
                 from public.production_orders o join public.parts p on p.id = o.part_id
                where o.tenant_id = %s and o.status = 'done' and o.material_cost is not null
                  and o.completed_at >= now() - make_interval(months => %s)
                group by o.part_id, p.name, p.part_no, p.unit
                order by sum(o.material_cost + o.labor_cost + o.machine_cost) desc, p.name""", [ctx.tenant_id, months]).fetchall()
        return {"months": months, "labor_cost_per_hour": thresholds(conn, ctx.tenant_id)["labor_cost_per_hour"],
                "products": products}
