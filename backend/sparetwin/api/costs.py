"""Toplam sahip olma maliyeti (Faz 2): makine bazında, seçilen dönemde.

Kalemler (hepsi kayıtlardan okunur, tahmin yok):
  parça     : dönemde bu makineye İLK kez takılan seri numaralı parçaların alış bedeli (rotasyon tekrar sayılmaz).
              İlk kurulumda Excel ile içe aktarılan parçalar sayılmaz: onlar o dönemin harcaması değil,
              sisteme girişten önce takılmış parçalardır.
  sarf      : bu makineye yapılan stok çıkışları (ortalama maliyetle)
  servis    : parça olaylarına girilen bedeller (tamir, muayene…) — makinedeyken yapılanlar
  bakım     : bakım kayıtlarındaki işçilik
  duruş     : duruş kayıtlarındaki tamir/servis bedeli; ayrıca duruş saati
Saat başı maliyet = toplam / dönemde çalışılan motor saati (motor saati geçmişinden).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from .deps import TenantCtx

router = APIRouter(prefix="/costs", tags=["Maliyet"])

SQL = """
with a as (
  select a.id, a.code, a.meter_hours, am.manufacturer, am.model
    from public.assets a left join public.asset_models am on am.id = a.model_id
   where a.tenant_id = %(t)s and (%(a)s::uuid is null or a.id = %(a)s)
),
parts as (
  select pe.asset_id, sum(pi.purchase_cost) as v, count(*) as n
    from public.part_events pe join public.part_items pi on pi.id = pe.part_item_id
   where pe.tenant_id = %(t)s and pe.event_type = 'installed' and (%(f)s::timestamptz is null or pe.occurred_at >= %(f)s)
     and coalesce(pe.notes, '') <> 'Excel içe aktarma'
     and not exists (select 1 from public.part_events p2 where p2.part_item_id = pe.part_item_id and p2.asset_id = pe.asset_id
                       and p2.event_type = 'installed' and p2.occurred_at < pe.occurred_at)
   group by pe.asset_id
),
consumables as (
  select sm.asset_id, sum(-sm.qty * coalesce(sm.unit_cost, 0)) as v
    from public.stock_movements sm
   where sm.tenant_id = %(t)s and sm.kind = 'out' and sm.asset_id is not null
     and (%(f)s::timestamptz is null or sm.occurred_at >= %(f)s)
   group by sm.asset_id
),
services as (
  select pe.asset_id, sum(pe.cost) as v
    from public.part_events pe
   where pe.tenant_id = %(t)s and pe.event_type <> 'installed' and pe.cost is not null and pe.asset_id is not null
     and (%(f)s::timestamptz is null or pe.occurred_at >= %(f)s)
   group by pe.asset_id
),
maint as (
  select r.asset_id, sum(coalesce(r.labor_cost, 0)) as v, count(*) as n
    from public.maintenance_records r
   where r.tenant_id = %(t)s and (%(f)s::timestamptz is null or r.performed_at >= %(f)s)
   group by r.asset_id
),
down as (
  select d.asset_id, sum(coalesce(d.cost, 0)) as v,
         sum(extract(epoch from coalesce(d.ended_at, now())
               - greatest(d.started_at, coalesce(%(f)s::timestamptz, d.started_at))) / 3600.0) as hours
    from public.downtime_events d
   where d.tenant_id = %(t)s and (%(f)s::timestamptz is null or coalesce(d.ended_at, now()) >= %(f)s)
   group by d.asset_id
),
start_meter as (
  -- Dönem başındaki motor saati: başlangıçtan önceki son okuma, yoksa dönemdeki ilk okuma
  select a.id as asset_id, coalesce(
    (select m.hours from public.meter_readings m where m.asset_id = a.id and m.hours is not null
       and %(f)s::timestamptz is not null and m.read_at <= %(f)s order by m.read_at desc limit 1),
    (select m.hours from public.meter_readings m where m.asset_id = a.id and m.hours is not null
       and (%(f)s::timestamptz is null or m.read_at >= %(f)s) order by m.read_at limit 1)) as hours
    from a
)
select a.id, a.code, a.manufacturer, a.model, a.meter_hours,
       coalesce(parts.v, 0) as parts, coalesce(parts.n, 0) as parts_count,
       coalesce(consumables.v, 0) as consumables,
       coalesce(services.v, 0) as services,
       coalesce(maint.v, 0) as maintenance, coalesce(maint.n, 0) as maintenance_count,
       coalesce(down.v, 0) as downtime_cost, round(coalesce(down.hours, 0)::numeric, 1) as downtime_hours,
       greatest(a.meter_hours - sm.hours, 0) as hours_worked
  from a
  left join parts on parts.asset_id = a.id
  left join consumables on consumables.asset_id = a.id
  left join services on services.asset_id = a.id
  left join maint on maint.asset_id = a.id
  left join down on down.asset_id = a.id
  left join start_meter sm on sm.asset_id = a.id
 order by a.code
"""


def _rows(ctx, days: int | None, asset_id: UUID | None = None):
    since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    with ctx.tx() as conn:
        rows = conn.execute(SQL, {"t": ctx.tenant_id, "a": asset_id, "f": since}).fetchall()
    for r in rows:
        r["total"] = r["parts"] + r["consumables"] + r["services"] + r["maintenance"] + r["downtime_cost"]
        r["cost_per_hour"] = round(r["total"] / r["hours_worked"], 2) if r["hours_worked"] else None
    return rows, since


@router.get("/assets", summary="Makine bazında toplam sahip olma maliyeti (dönem: son N gün; boşsa tümü)")
def by_asset(ctx: TenantCtx, days: int = Query(90, ge=0, le=3650, description="0: tüm zamanlar")):
    rows, since = _rows(ctx, days)
    keys = ("parts", "consumables", "services", "maintenance", "downtime_cost", "total", "hours_worked", "downtime_hours")
    totals = {k: sum(r[k] or 0 for r in rows) for k in keys}
    totals["cost_per_hour"] = round(totals["total"] / totals["hours_worked"], 2) if totals["hours_worked"] else None
    return {"since": since, "days": days, "rows": rows, "totals": totals}


@router.get("/assets/{asset_id}", summary="Tek makinenin maliyet dökümü")
def one(asset_id: UUID, ctx: TenantCtx, days: int = Query(90, ge=0, le=3650)):
    rows, since = _rows(ctx, days, asset_id)
    if not rows:
        raise HTTPException(404, "Makine bulunamadı")
    return {"since": since, "days": days, **rows[0]}
