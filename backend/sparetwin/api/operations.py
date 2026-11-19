"""Bakım planları, bakım kayıtları ve arıza/duruş (Faz 2)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, model_validator

from .deps import TenantCtx

router = APIRouter(tags=["Bakım ve duruş"])


# ---------- Bakım planları ----------
class Material(BaseModel):
    part_id: UUID
    qty: Decimal = Field(gt=0, le=100_000)


class PlanIn(BaseModel):
    asset_id: UUID
    name: str = Field(min_length=2, max_length=120)
    interval_hours: Decimal | None = Field(None, gt=0, le=100_000)
    interval_days: int | None = Field(None, gt=0, le=3650)
    last_done_hours: Decimal | None = Field(None, ge=0, description="Boşsa makinenin güncel saati")
    last_done_at: datetime | None = Field(None, description="Boşsa şimdi")
    materials: list[Material] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def one_interval(self):
        if self.interval_hours is None and self.interval_days is None:
            raise ValueError("Saat veya gün periyodundan en az biri gerekli")
        return self


class PlanPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    interval_hours: Decimal | None = Field(None, gt=0)
    interval_days: int | None = Field(None, gt=0)
    materials: list[Material] | None = None
    notes: str | None = Field(None, max_length=1000)
    active: bool | None = None


class CompleteIn(BaseModel):
    asset_hours: Decimal | None = Field(None, ge=0, description="Boşsa makinenin güncel saati")
    labor_cost: Decimal | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=2000)
    site_id: UUID | None = Field(None, description="Malzemelerin çıkılacağı depo")
    consume_materials: bool = True


class RecordIn(BaseModel):
    asset_id: UUID
    title: str = Field(min_length=2, max_length=160)
    asset_hours: Decimal | None = Field(None, ge=0)
    labor_cost: Decimal | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=2000)


def _asset(conn, asset_id: UUID, tenant_id: UUID) -> dict:
    a = conn.execute("select id, code, meter_hours from public.assets where id = %s and tenant_id = %s",
                     [asset_id, tenant_id]).fetchone()
    if not a:
        raise HTTPException(404, "Makine bulunamadı")
    return a


def _check_materials(conn, materials: list[Material], tenant_id: UUID) -> list[dict]:
    out = []
    for m in materials:
        p = conn.execute(
            """select p.id, pc.is_serialized from public.parts p join public.part_categories pc on pc.id = p.category_id
                where p.id = %s and (p.tenant_id = %s or p.tenant_id is null)""", [m.part_id, tenant_id]).fetchone()
        if not p:
            raise HTTPException(404, "Malzeme katalogda bulunamadı")
        if p["is_serialized"]:
            raise HTTPException(422, "Bakım malzemesi sarf olmalı (filtre, yağ, keçe…); seri numaralı parçalar takma/sökme ile değişir")
        out.append({"part_id": str(m.part_id), "qty": float(m.qty)})
    return out


@router.get("/maintenance/plans", summary="Bakım planları ve durumları (gecikmiş / yaklaşan / güncel)")
def plans(ctx: TenantCtx, asset_id: UUID | None = None, status: str | None = None):
    with ctx.tx() as conn:
        rows = conn.execute(
            """select d.* from public.v_maintenance_due d
                where d.tenant_id = %(t)s and (%(a)s::uuid is null or d.asset_id = %(a)s)
                  and (%(s)s::text is null or d.due_status = %(s)s)
                order by case d.due_status when 'overdue' then 0 when 'due_soon' then 1 when 'ok' then 2 else 3 end,
                         d.hours_left nulls last, d.days_left nulls last, d.asset_code""",
            {"t": ctx.tenant_id, "a": asset_id, "s": status}).fetchall()
        names = {r["id"]: r for r in conn.execute(
            "select id, name, unit from public.parts where tenant_id = %s or tenant_id is null", [ctx.tenant_id]).fetchall()}
    for r in rows:
        r["materials"] = [{**m, "name": names.get(UUID(m["part_id"]), {}).get("name"),
                           "unit": names.get(UUID(m["part_id"]), {}).get("unit")} for m in r["materials"]]
    return rows


@router.post("/maintenance/plans", status_code=201, summary="Bakım planı ekle (yönetici)")
def create_plan(body: PlanIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        a = _asset(conn, body.asset_id, ctx.tenant_id)
        mats = _check_materials(conn, body.materials, ctx.tenant_id)
        return conn.execute(
            """insert into public.maintenance_plans
                 (tenant_id, asset_id, name, interval_hours, interval_days, last_done_hours, last_done_at, materials, notes)
               values (%s, %s, %s, %s, %s, %s, coalesce(%s, now()), %s, %s) returning id, name""",
            [ctx.tenant_id, a["id"], body.name, body.interval_hours, body.interval_days,
             body.last_done_hours if body.last_done_hours is not None else a["meter_hours"],
             body.last_done_at, Jsonb(mats), body.notes]).fetchone()


@router.patch("/maintenance/plans/{plan_id}", summary="Bakım planını değiştir (yönetici)")
def patch_plan(plan_id: UUID, body: PlanPatch, ctx: TenantCtx):
    ctx.require("manager")
    fields = body.model_dump(exclude_unset=True)
    with ctx.tx() as conn:
        if "materials" in fields:
            fields["materials"] = Jsonb(_check_materials(conn, body.materials or [], ctx.tenant_id))
        if not fields:
            return {"id": plan_id}
        sets = ", ".join(f"{k} = %({k})s" for k in fields)  # anahtarlar modelden
        r = conn.execute(f"update public.maintenance_plans set {sets} where id = %(id)s and tenant_id = %(t)s",
                         {**fields, "id": plan_id, "t": ctx.tenant_id})
        if r.rowcount == 0:
            raise HTTPException(404, "Plan bulunamadı")
        return {"id": plan_id}


@router.post("/maintenance/plans/{plan_id}/complete", summary="Bakım yapıldı: kayıt açılır, plan sıfırlanır, malzeme stoktan düşer")
def complete(plan_id: UUID, body: CompleteIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:  # malzeme stokta yoksa hiçbir şey yazılmaz
        p = conn.execute("select * from public.maintenance_plans where id = %s and tenant_id = %s for update",
                         [plan_id, ctx.tenant_id]).fetchone()
        if not p:
            raise HTTPException(404, "Plan bulunamadı")
        a = _asset(conn, p["asset_id"], ctx.tenant_id)
        hours = body.asset_hours if body.asset_hours is not None else a["meter_hours"]
        if hours > a["meter_hours"]:
            conn.execute("select 1 from public.record_meter_reading(%s, %s)", [a["id"], hours])
        rec = conn.execute(
            """insert into public.maintenance_records (tenant_id, asset_id, plan_id, title, asset_hours, labor_cost, notes, performed_by)
               values (%s, %s, %s, %s, %s, %s, %s, %s) returning id, performed_at""",
            [ctx.tenant_id, a["id"], plan_id, p["name"], hours, body.labor_cost, body.notes, ctx.user_id]).fetchone()
        conn.execute("update public.maintenance_plans set last_done_hours = %s, last_done_at = now() where id = %s", [hours, plan_id])
        consumed = []
        if body.consume_materials:
            for m in p["materials"]:
                # JSON'dan gelen değerler açıkça tiplenir (metin → uuid, ondalık → numeric)
                conn.execute("select 1 from public.stock_move(%s::uuid, %s, 'out', %s::numeric, null, %s, 'bakım', null, %s, null, %s)",
                             [m["part_id"], body.site_id, m["qty"], a["id"], p["name"], ctx.tenant_id])
                consumed.append(m)
        return {"record_id": rec["id"], "asset_hours": hours, "consumed": consumed}


@router.post("/maintenance/records", status_code=201, summary="Plansız bakım / onarım kaydı")
def add_record(body: RecordIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        a = _asset(conn, body.asset_id, ctx.tenant_id)
        return conn.execute(
            """insert into public.maintenance_records (tenant_id, asset_id, title, asset_hours, labor_cost, notes, performed_by)
               values (%s, %s, %s, %s, %s, %s, %s) returning id""",
            [ctx.tenant_id, a["id"], body.title, body.asset_hours if body.asset_hours is not None else a["meter_hours"],
             body.labor_cost, body.notes, ctx.user_id]).fetchone()


@router.get("/maintenance/records", summary="Bakım kayıtları")
def records(ctx: TenantCtx, asset_id: UUID | None = None, limit: int = Query(100, ge=1, le=500)):
    with ctx.tx() as conn:
        return conn.execute(
            """select r.*, a.code as asset_code, u.full_name as performed_by_name
                 from public.maintenance_records r join public.assets a on a.id = r.asset_id
                 left join public.app_users u on u.id = r.performed_by
                where r.tenant_id = %s and (%s::uuid is null or r.asset_id = %s)
                order by r.performed_at desc limit %s""", [ctx.tenant_id, asset_id, asset_id, limit]).fetchall()


# ---------- Arıza / duruş ----------
Category = Literal["breakdown", "planned_maintenance", "tire", "waiting_parts", "operational", "other"]


class DowntimeIn(BaseModel):
    asset_id: UUID
    category: Category
    description: str | None = Field(None, max_length=1000)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    cost: Decimal | None = Field(None, ge=0)
    part_item_id: UUID | None = None


class DowntimeEnd(BaseModel):
    ended_at: datetime | None = None
    cost: Decimal | None = Field(None, ge=0)
    description: str | None = Field(None, max_length=1000)


@router.get("/downtime", summary="Duruşlar (açık olanlar önce)")
def downtime(ctx: TenantCtx, asset_id: UUID | None = None, open: bool | None = None, limit: int = Query(100, ge=1, le=500)):
    with ctx.tx() as conn:
        return conn.execute(
            """select d.*, a.code as asset_code,
                      round(extract(epoch from coalesce(d.ended_at, now()) - d.started_at) / 3600.0, 1) as hours
                 from public.downtime_events d join public.assets a on a.id = d.asset_id
                where d.tenant_id = %(t)s and (%(a)s::uuid is null or d.asset_id = %(a)s)
                  and (%(o)s::boolean is null or (d.ended_at is null) = %(o)s)
                order by (d.ended_at is null) desc, d.started_at desc limit %(l)s""",
            {"t": ctx.tenant_id, "a": asset_id, "o": open, "l": limit}).fetchall()


@router.post("/downtime", status_code=201, summary="Duruş başlat (veya bitmiş bir duruşu kaydet)")
def start_downtime(body: DowntimeIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        a = _asset(conn, body.asset_id, ctx.tenant_id)
        if body.ended_at is None and conn.execute(
                "select 1 from public.downtime_events where asset_id = %s and ended_at is null", [a["id"]]).fetchone():
            raise HTTPException(409, f"{a['code']} zaten duruşta; önce açık duruşu bitirin")
        if body.started_at and body.ended_at and body.ended_at < body.started_at:
            raise HTTPException(422, "Bitiş, başlangıçtan önce olamaz")
        return conn.execute(
            """insert into public.downtime_events (tenant_id, asset_id, category, part_item_id, description, started_at, ended_at, cost, created_by)
               values (%s, %s, %s, %s, %s, coalesce(%s, now()), %s, %s, %s) returning id, started_at, ended_at""",
            [ctx.tenant_id, a["id"], body.category, body.part_item_id, body.description, body.started_at,
             body.ended_at, body.cost, ctx.user_id]).fetchone()


@router.post("/downtime/{downtime_id}/end", summary="Duruşu bitir: makine tekrar çalışıyor")
def end_downtime(downtime_id: UUID, body: DowntimeEnd, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        d = conn.execute("select * from public.downtime_events where id = %s and tenant_id = %s for update",
                         [downtime_id, ctx.tenant_id]).fetchone()
        if not d:
            raise HTTPException(404, "Duruş bulunamadı")
        if d["ended_at"]:
            raise HTTPException(409, "Bu duruş zaten bitmiş")
        end = body.ended_at or datetime.now(d["started_at"].tzinfo)
        if end < d["started_at"]:
            raise HTTPException(422, "Bitiş, başlangıçtan önce olamaz")
        return conn.execute(
            """update public.downtime_events set ended_at = %s, cost = coalesce(%s, cost),
                      description = coalesce(%s, description) where id = %s
               returning id, ended_at, round(extract(epoch from ended_at - started_at) / 3600.0, 1) as hours""",
            [end, body.cost, body.description, downtime_id]).fetchone()
