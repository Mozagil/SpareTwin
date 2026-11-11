"""Bakım (Faz 2): bakım planları, sıradaki bakımlar, iş emirleri (planlı ve arıza).

Yetki: listeleme herkes; iş emri açma, düzenleme, başlatma ve tamamlama teknisyen ve üstü;
emir iptali ve plan yönetimi yönetici (manager) ve üstü.
Kurallar (durum geçişleri, makine durumu, stoktan düşme, sıradaki bakım) veritabanında (0015).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, model_validator

from .deps import TenantCtx

router = APIRouter(prefix="/maintenance", tags=["Bakım"])

WoKind = Literal["planned", "breakdown"]
WoStatus = Literal["open", "in_progress", "done", "cancelled"]
DueState = Literal["overdue", "due_soon", "ok"]
ReasonCode = Literal["hydraulic", "electrical", "engine", "tire", "transmission", "structural", "operator", "other"]


# ---------- Plan ----------
class PlanPartIn(BaseModel):
    part_id: UUID
    qty: Decimal = Field(gt=0, le=1_000_000)


class PlanIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    asset_id: UUID | None = Field(None, description="Tek makine için plan")
    model_id: UUID | None = Field(None, description="Modelin tüm makineleri için plan")
    interval_hours: Decimal | None = Field(None, gt=0, le=100_000)
    interval_days: int | None = Field(None, gt=0, le=3650)
    checklist: list[str] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(None, max_length=1000)
    is_active: bool = True
    parts: list[PlanPartIn] = Field(default_factory=list, max_length=50, description="Her bakımda kullanılan sarf")

    @model_validator(mode="after")
    def _rules(self):
        if (self.asset_id is None) == (self.model_id is None):
            raise ValueError("Plan ya bir makineye ya bir modele bağlanır (ikisinden biri)")
        if self.interval_hours is None and self.interval_days is None:
            raise ValueError("Saat ya da gün periyodundan en az biri gerekir")
        self.checklist = [c.strip()[:160] for c in self.checklist if c and c.strip()]
        ids = [p.part_id for p in self.parts]
        if len(ids) != len(set(ids)):
            raise ValueError("Aynı kalem listede birden fazla kez var")
        return self


PLAN_LIST_SQL = """
select p.id, p.name, p.asset_id, a.code as asset_code, p.model_id, am.manufacturer || ' ' || am.model as model_name,
       p.interval_hours, p.interval_days, p.checklist, p.notes, p.is_active, p.created_at, p.updated_at,
       (select count(*) from public.assets x where x.tenant_id = p.tenant_id and x.status <> 'retired'
          and (x.id = p.asset_id or (p.model_id is not null and x.model_id = p.model_id))) as asset_count,
       coalesce(pp.parts, '[]'::jsonb) as parts
  from public.maintenance_plans p
  left join public.assets a on a.id = p.asset_id
  left join public.asset_models am on am.id = p.model_id
  left join lateral (
    select jsonb_agg(jsonb_build_object('part_id', pp.part_id, 'name', pt.name, 'unit', pt.unit, 'qty', pp.qty,
                                        'is_serialized', pc.is_serialized) order by pt.name) as parts
      from public.maintenance_plan_parts pp
      join public.parts pt on pt.id = pp.part_id
      join public.part_categories pc on pc.id = pt.category_id
     where pp.plan_id = p.id
  ) pp on true
"""


@router.get("/plans", summary="Bakım planları")
def plans(ctx: TenantCtx, include_inactive: bool = False, asset_id: UUID | None = None):
    with ctx.tx() as conn:
        return conn.execute(
            PLAN_LIST_SQL + """
             where p.tenant_id = %(t)s and (%(all)s or p.is_active)
               and (%(a)s::uuid is null or p.asset_id = %(a)s
                    or p.model_id = (select model_id from public.assets where id = %(a)s))
             order by p.is_active desc, p.name""",
            {"t": ctx.tenant_id, "all": include_inactive, "a": asset_id},
        ).fetchall()


def _plan(conn, plan_id: UUID, tenant_id: UUID) -> dict:
    row = conn.execute(PLAN_LIST_SQL + " where p.id = %s and p.tenant_id = %s", [plan_id, tenant_id]).fetchone()
    if not row:
        raise HTTPException(404, "Bakım planı bulunamadı")
    return row


def _check_plan_refs(conn, ctx: TenantCtx, body: PlanIn) -> None:
    if body.asset_id and not conn.execute("select 1 from public.assets where id = %s and tenant_id = %s",
                                          [body.asset_id, ctx.tenant_id]).fetchone():
        raise HTTPException(404, "Makine bulunamadı")
    if body.model_id and not conn.execute(
            "select 1 from public.asset_models where id = %s and (tenant_id = %s or tenant_id is null)",
            [body.model_id, ctx.tenant_id]).fetchone():
        raise HTTPException(404, "Makine modeli bulunamadı")
    for p in body.parts:
        r = conn.execute(
            """select pc.is_serialized from public.parts p join public.part_categories pc on pc.id = p.category_id
                where p.id = %s and (p.tenant_id = %s or p.tenant_id is null)""", [p.part_id, ctx.tenant_id]).fetchone()
        if not r:
            raise HTTPException(404, "Katalog kalemi bulunamadı")
        if r["is_serialized"]:
            raise HTTPException(422, "Seri numaralı parçalar bakım sarf listesine girmez; değişimi parça tak/sök ile yapılır")


def _save_plan_parts(conn, ctx: TenantCtx, plan_id: UUID, parts: list[PlanPartIn]) -> None:
    conn.execute("delete from public.maintenance_plan_parts where plan_id = %s", [plan_id])
    for p in parts:
        conn.execute("insert into public.maintenance_plan_parts (tenant_id, plan_id, part_id, qty) values (%s, %s, %s, %s)",
                     [ctx.tenant_id, plan_id, p.part_id, p.qty])


@router.post("/plans", status_code=201, summary="Bakım planı ekle")
def plan_create(body: PlanIn, ctx: TenantCtx, request: Request):
    ctx.require("manager")
    with ctx.tx() as conn:
        _check_plan_refs(conn, ctx, body)
        row = conn.execute(
            """insert into public.maintenance_plans
                 (tenant_id, name, asset_id, model_id, interval_hours, interval_days, checklist, notes, is_active, created_by)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
            [ctx.tenant_id, body.name, body.asset_id, body.model_id, body.interval_hours, body.interval_days,
             Jsonb(body.checklist), body.notes, body.is_active, ctx.user_id],
        ).fetchone()
        _save_plan_parts(conn, ctx, row["id"], body.parts)
        request.state.audit = {"name": body.name}
        return _plan(conn, row["id"], ctx.tenant_id)


@router.patch("/plans/{plan_id}", summary="Bakım planını güncelle (pasife alma dahil)")
def plan_update(plan_id: UUID, body: PlanIn, ctx: TenantCtx, request: Request):
    ctx.require("manager")
    with ctx.tx() as conn:
        _check_plan_refs(conn, ctx, body)
        row = conn.execute(
            """update public.maintenance_plans
                  set name = %s, asset_id = %s, model_id = %s, interval_hours = %s, interval_days = %s,
                      checklist = %s, notes = %s, is_active = %s
                where id = %s and tenant_id = %s returning id""",
            [body.name, body.asset_id, body.model_id, body.interval_hours, body.interval_days, Jsonb(body.checklist),
             body.notes, body.is_active, plan_id, ctx.tenant_id],
        ).fetchone()
        if not row:
            raise HTTPException(404, "Bakım planı bulunamadı")
        _save_plan_parts(conn, ctx, plan_id, body.parts)
        request.state.audit = {"name": body.name, "is_active": body.is_active}
        return _plan(conn, plan_id, ctx.tenant_id)


# ---------- Sıradaki bakımlar ----------
@router.get("/due", summary="Sıradaki bakımlar: plan × makine, kalan saat/gün, durum")
def due(ctx: TenantCtx, asset_id: UUID | None = None, state: DueState | None = None):
    with ctx.tx() as conn:
        return conn.execute(
            """select * from public.v_maintenance_due
                where tenant_id = %(t)s and (%(a)s::uuid is null or asset_id = %(a)s) and (%(s)s::text is null or state = %(s)s)
                order by case state when 'overdue' then 0 when 'due_soon' then 1 else 2 end,
                         least(coalesce(hours_left / 24, 1e9), coalesce(days_left, 1e9)), asset_code, name""",
            {"t": ctx.tenant_id, "a": asset_id, "s": state},
        ).fetchall()


@router.get("/summary", summary="Makine başına bakım özeti: emir sayıları, duruş, son 12 ay maliyet")
def summary(ctx: TenantCtx):
    with ctx.tx() as conn:
        return conn.execute(
            """select m.*, a.status as asset_status from public.v_asset_maintenance m
                 join public.assets a on a.id = m.asset_id
                where m.tenant_id = %s and a.status <> 'retired'
                order by m.open_orders desc, m.downtime_minutes desc, m.asset_code""", [ctx.tenant_id]).fetchall()


# ---------- İş emri ----------
class WoPartIn(BaseModel):
    part_id: UUID
    qty: Decimal = Field(gt=0, le=1_000_000)
    site_id: UUID | None = Field(None, description="Hangi depodan düşer; boşsa genel depo")


class WorkOrderIn(BaseModel):
    asset_id: UUID
    kind: WoKind = "planned"
    plan_id: UUID | None = Field(None, description="Planlı bakımda hangi plan; başlık ve sarf plandan gelir")
    title: str | None = Field(None, min_length=2, max_length=160)
    description: str | None = Field(None, max_length=2000)
    due_at: date | None = None
    due_hours: Decimal | None = Field(None, ge=0)
    down_from: datetime | None = Field(None, description="Arıza: makine ne zaman durdu (boşsa şimdi)")
    reason_code: ReasonCode | None = None
    part_item_id: UUID | None = Field(None, description="Arızayla ilgili parça")
    assigned_to: UUID | None = None
    parts: list[WoPartIn] | None = Field(None, max_length=50, description="Boşsa plandaki sarf listesi")

    @model_validator(mode="after")
    def _rules(self):
        if self.kind == "planned" and not self.plan_id and not self.title:
            raise ValueError("Planlı emirde plan ya da başlık gerekir")
        if self.kind == "breakdown" and not self.title:
            raise ValueError("Arıza emrinde başlık gerekir (ne oldu?)")
        if self.parts:
            ids = [p.part_id for p in self.parts]
            if len(ids) != len(set(ids)):
                raise ValueError("Aynı kalem listede birden fazla kez var")
        return self


class WorkOrderPatch(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=160)
    description: str | None = Field(None, max_length=2000)
    due_at: date | None = None
    due_hours: Decimal | None = Field(None, ge=0)
    down_from: datetime | None = None
    reason_code: ReasonCode | None = None
    part_item_id: UUID | None = None
    assigned_to: UUID | None = None
    labor_cost: Decimal | None = Field(None, ge=0)
    external_cost: Decimal | None = Field(None, ge=0)
    parts: list[WoPartIn] | None = Field(None, max_length=50, description="Verilirse sarf listesi tümden değişir")

    @model_validator(mode="after")
    def _unique(self):
        if self.parts:
            ids = [p.part_id for p in self.parts]
            if len(ids) != len(set(ids)):
                raise ValueError("Aynı kalem listede birden fazla kez var")
        return self


class WoStatusIn(BaseModel):
    status: Literal["in_progress", "done", "cancelled"] = Field(
        description="in_progress: başla, done: tamamla (sarf stoktan düşer), cancelled: iptal")
    asset_hours: Decimal | None = Field(None, ge=0, description="Tamamlarken makine saati; sayaçtan büyükse sayaç güncellenir")
    down_to: datetime | None = Field(None, description="Arıza: çalışmaya dönüş zamanı (boşsa şimdi)")
    labor_cost: Decimal | None = Field(None, ge=0)
    external_cost: Decimal | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=2000, description="Yapılan iş; açıklamaya eklenir")


WO_LIST_SQL = """
select w.id, w.number, w.kind, w.status, w.title, w.asset_id, a.code as asset_code, a.meter_hours as asset_meter_hours,
       w.plan_id, p.name as plan_name, w.due_at, w.due_hours, w.down_from, w.down_to, w.downtime_minutes, w.reason_code,
       w.part_item_id, pi.serial_no as part_serial_no, pt.name as part_name,
       w.asset_hours_at_done, w.labor_cost, w.external_cost, w.started_at, w.completed_at, w.created_at, w.updated_at,
       cu.full_name as created_by_name, au.full_name as assigned_to_name, du.full_name as completed_by_name,
       w.assigned_to, w.description,
       wp.part_count, wp.parts_cost,
       (w.status in ('open', 'in_progress') and (coalesce(w.due_at < current_date, false) or coalesce(w.due_hours < a.meter_hours, false))) as late
  from public.work_orders w
  join public.assets a on a.id = w.asset_id
  left join public.maintenance_plans p on p.id = w.plan_id
  left join public.part_items pi on pi.id = w.part_item_id
  left join public.parts pt on pt.id = pi.part_id
  left join public.app_users cu on cu.id = w.created_by
  left join public.app_users au on au.id = w.assigned_to
  left join public.app_users du on du.id = w.completed_by
  left join lateral (
    select count(*) as part_count, sum(x.qty * coalesce(x.unit_cost, st.avg_cost, pt2.list_cost, 0)) as parts_cost
      from public.work_order_parts x
      join public.parts pt2 on pt2.id = x.part_id
      left join public.v_stock_totals st on st.tenant_id = x.tenant_id and st.part_id = x.part_id
     where x.work_order_id = w.id
  ) wp on true
"""


@router.get("/work-orders", summary="İş emirleri")
def work_orders(
    ctx: TenantCtx,
    status: WoStatus | None = None,
    kind: WoKind | None = None,
    asset_id: UUID | None = None,
    open_only: bool = Query(False, description="Yalnızca açık ve süren emirler"),
    q: str | None = Query(None, max_length=60),
    limit: int = Query(200, ge=1, le=500),
):
    with ctx.tx() as conn:
        return conn.execute(
            WO_LIST_SQL + """
             where w.tenant_id = %(t)s
               and (%(s)s::text is null or w.status::text = %(s)s)
               and (%(k)s::text is null or w.kind::text = %(k)s)
               and (%(a)s::uuid is null or w.asset_id = %(a)s)
               and (not %(o)s or w.status in ('open', 'in_progress'))
               and (%(q)s::text is null or w.number ilike '%%' || %(q)s || '%%' or w.title ilike '%%' || %(q)s || '%%'
                    or a.code ilike '%%' || %(q)s || '%%')
             order by (w.status in ('open', 'in_progress')) desc, (w.kind = 'breakdown') desc,
                      coalesce(w.due_at, current_date + 3650), w.created_at desc
             limit %(lim)s""",
            {"t": ctx.tenant_id, "s": status, "k": kind, "a": asset_id, "o": open_only, "q": q, "lim": limit},
        ).fetchall()


def _wo(conn, wo_id: UUID, tenant_id: UUID) -> dict:
    w = conn.execute(WO_LIST_SQL + " where w.id = %s and w.tenant_id = %s", [wo_id, tenant_id]).fetchone()
    if not w:
        raise HTTPException(404, "İş emri bulunamadı")
    w["parts"] = conn.execute(
        """select x.id, x.part_id, pt.name, pt.unit, x.qty, x.site_id, s.name as site_name,
                  coalesce(x.unit_cost, st.avg_cost, pt.list_cost) as unit_cost,
                  coalesce(app.stock_level(x.tenant_id, x.part_id, x.site_id), 0) as in_stock
             from public.work_order_parts x
             join public.parts pt on pt.id = x.part_id
             left join public.sites s on s.id = x.site_id
             left join public.v_stock_totals st on st.tenant_id = x.tenant_id and st.part_id = x.part_id
            where x.work_order_id = %s order by pt.name""", [wo_id]).fetchall()
    w["checklist"] = (conn.execute("select checklist from public.maintenance_plans where id = %s", [w["plan_id"]]).fetchone()
                      or {}).get("checklist") if w["plan_id"] else None
    return w


def _check_wo_refs(conn, ctx: TenantCtx, asset_id: UUID | None, plan_id: UUID | None, part_item_id: UUID | None,
                   assigned_to: UUID | None, parts: list[WoPartIn] | None) -> None:
    if asset_id and not conn.execute("select 1 from public.assets where id = %s and tenant_id = %s",
                                     [asset_id, ctx.tenant_id]).fetchone():
        raise HTTPException(404, "Makine bulunamadı")
    if plan_id and not conn.execute("select 1 from public.maintenance_plans where id = %s and tenant_id = %s",
                                    [plan_id, ctx.tenant_id]).fetchone():
        raise HTTPException(404, "Bakım planı bulunamadı")
    if part_item_id and not conn.execute("select 1 from public.part_items where id = %s and tenant_id = %s",
                                         [part_item_id, ctx.tenant_id]).fetchone():
        raise HTTPException(404, "Parça bulunamadı")
    if assigned_to and not conn.execute("select 1 from public.memberships where user_id = %s and tenant_id = %s",
                                        [assigned_to, ctx.tenant_id]).fetchone():
        raise HTTPException(404, "Kullanıcı bu firmanın üyesi değil")
    for p in parts or []:
        r = conn.execute(
            """select pc.is_serialized from public.parts p join public.part_categories pc on pc.id = p.category_id
                where p.id = %s and (p.tenant_id = %s or p.tenant_id is null)""", [p.part_id, ctx.tenant_id]).fetchone()
        if not r:
            raise HTTPException(404, "Katalog kalemi bulunamadı")
        if r["is_serialized"]:
            raise HTTPException(422, "Seri numaralı parça emrin sarf listesine girmez; makine sayfasından tak/sök yapın")
        if p.site_id and not conn.execute("select 1 from public.sites where id = %s and tenant_id = %s",
                                          [p.site_id, ctx.tenant_id]).fetchone():
            raise HTTPException(404, "Depo bulunamadı")


def _save_wo_parts(conn, ctx: TenantCtx, wo_id: UUID, parts: list[WoPartIn]) -> None:
    conn.execute("delete from public.work_order_parts where work_order_id = %s", [wo_id])
    for p in parts:
        conn.execute("insert into public.work_order_parts (tenant_id, work_order_id, part_id, qty, site_id) values (%s, %s, %s, %s, %s)",
                     [ctx.tenant_id, wo_id, p.part_id, p.qty, p.site_id])


@router.get("/work-orders/{wo_id}", summary="İş emri ayrıntısı: sarf listesi, kontrol listesi")
def work_order_get(wo_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        return _wo(conn, wo_id, ctx.tenant_id)


@router.post("/work-orders", status_code=201, summary="İş emri aç (planlı bakım ya da arıza)")
def work_order_create(body: WorkOrderIn, ctx: TenantCtx, request: Request):
    ctx.require("technician")
    with ctx.tx() as conn:
        _check_wo_refs(conn, ctx, body.asset_id, body.plan_id, body.part_item_id, body.assigned_to, body.parts)
        title, due_at, due_hours, parts = body.title, body.due_at, body.due_hours, body.parts
        if body.plan_id:
            plan = conn.execute("select name from public.maintenance_plans where id = %s", [body.plan_id]).fetchone()
            title = title or plan["name"]
            d = conn.execute("select next_due_at, next_due_hours, site_id from public.v_maintenance_due where plan_id = %s and asset_id = %s",
                             [body.plan_id, body.asset_id]).fetchone()
            if d:
                due_at = due_at or d["next_due_at"]
                due_hours = due_hours if due_hours is not None else d["next_due_hours"]
            if parts is None:
                site = d["site_id"] if d else None
                parts = [WoPartIn(part_id=r["part_id"], qty=r["qty"], site_id=site) for r in conn.execute(
                    "select part_id, qty from public.maintenance_plan_parts where plan_id = %s", [body.plan_id]).fetchall()]
        down_from = (body.down_from or datetime.now().astimezone()) if body.kind == "breakdown" else None
        row = conn.execute(
            """insert into public.work_orders
                 (tenant_id, number, asset_id, plan_id, kind, title, description, due_at, due_hours, down_from,
                  reason_code, part_item_id, assigned_to, created_by)
               values (%s, app.next_wo_number(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id, number""",
            [ctx.tenant_id, ctx.tenant_id, body.asset_id, body.plan_id, body.kind, title, body.description, due_at, due_hours,
             down_from, body.reason_code, body.part_item_id, body.assigned_to, ctx.user_id],
        ).fetchone()
        _save_wo_parts(conn, ctx, row["id"], parts or [])
        request.state.audit = {"number": row["number"], "kind": body.kind, "title": title}
        return _wo(conn, row["id"], ctx.tenant_id)


@router.patch("/work-orders/{wo_id}", summary="İş emrini düzenle (açık ya da sürüyorken)")
def work_order_update(wo_id: UUID, body: WorkOrderPatch, ctx: TenantCtx, request: Request):
    ctx.require("technician")
    with ctx.tx() as conn:
        cur = conn.execute("select status, number from public.work_orders where id = %s and tenant_id = %s",
                           [wo_id, ctx.tenant_id]).fetchone()
        if not cur:
            raise HTTPException(404, "İş emri bulunamadı")
        if cur["status"] in ("done", "cancelled"):
            raise HTTPException(422, "Kapanmış emir düzenlenemez")
        _check_wo_refs(conn, ctx, None, None, body.part_item_id, body.assigned_to, body.parts)
        fields = body.model_dump(exclude_unset=True, exclude={"parts"})
        if fields:
            sets = ", ".join(f"{k} = %s" for k in fields)
            conn.execute(f"update public.work_orders set {sets} where id = %s", [*fields.values(), wo_id])
        if body.parts is not None:
            _save_wo_parts(conn, ctx, wo_id, body.parts)
        request.state.audit = {"number": cur["number"], "changed": sorted(fields) + (["parts"] if body.parts is not None else [])}
        return _wo(conn, wo_id, ctx.tenant_id)


@router.post("/work-orders/{wo_id}/status", summary="Başlat, tamamla (sarf stoktan düşer, makine saati güncellenir) veya iptal et")
def work_order_status(wo_id: UUID, body: WoStatusIn, ctx: TenantCtx, request: Request):
    ctx.require("manager" if body.status == "cancelled" else "technician")
    with ctx.tx() as conn:
        cur = conn.execute("select number, description from public.work_orders where id = %s and tenant_id = %s",
                           [wo_id, ctx.tenant_id]).fetchone()
        if not cur:
            raise HTTPException(404, "İş emri bulunamadı")
        extra = {k: v for k, v in (("labor_cost", body.labor_cost), ("external_cost", body.external_cost)) if v is not None}
        if body.notes:
            extra["description"] = ((cur["description"] + "\n\n") if cur["description"] else "") + body.notes.strip()
        if extra:
            sets = ", ".join(f"{k} = %s" for k in extra)
            conn.execute(f"update public.work_orders set {sets} where id = %s", [*extra.values(), wo_id])
        row = conn.execute("select number, status, downtime_minutes from public.wo_set_status(%s, %s, %s, %s)",
                           [wo_id, body.status, body.asset_hours, body.down_to]).fetchone()
        request.state.audit = {"number": row["number"], "status": row["status"],
                               **({"asset_hours": format(body.asset_hours.normalize(), "f")} if body.asset_hours is not None else {}),
                               **({"downtime_minutes": row["downtime_minutes"]} if row["downtime_minutes"] is not None else {})}
        return _wo(conn, wo_id, ctx.tenant_id)
