-- =====================================================================
-- SpareTwin — 0017: Makine bazlı duruş saat maliyeti (Faz 2)
-- ---------------------------------------------------------------------
-- Bir saatlik duruşun bedeli her makinede aynı değildir: gemiyi bekleten
-- istif makinesi ile yedek forklift bir tutulmaz.
-- assets.downtime_cost_per_hour boşsa firmanın oranı (0016) geçerlidir;
-- doluysa (0 dahil) o makinenin duruşu bu oranla çarpılır.
-- asset_tco() geçerli oranı (downtime_rate) ve makineye özel olup olmadığını
-- (downtime_rate_own) da döndürür. Dönüş tipi değiştiği için işlev yeniden kurulur;
-- gövdenin geri kalanı 0016 ile aynıdır.
-- =====================================================================

alter table public.assets
  add column downtime_cost_per_hour numeric(10,2)
    check (downtime_cost_per_hour >= 0 and downtime_cost_per_hour <= 100000);

comment on column public.assets.downtime_cost_per_hour is
  'Makineye özel duruş saat maliyeti; boşsa tenants.settings thresholds.downtime_cost_per_hour';

drop function public.asset_tco(uuid, timestamptz, timestamptz);

create function public.asset_tco(p_tenant uuid, p_from timestamptz, p_to timestamptz default now())
returns table (
  asset_id uuid, asset_code text, asset_status app.asset_status, site_id uuid, site_name text, model_name text,
  parts_cost numeric, consumables_cost numeric, labor_cost numeric, external_cost numeric,
  downtime_minutes integer, downtime_cost numeric, total numeric,
  planned_done integer, breakdowns integer,
  hours_worked numeric, hours_from timestamptz, cost_per_hour numeric,
  downtime_rate numeric, downtime_rate_own boolean
)
language sql stable security invoker
set search_path = public, app
as $$
with rate as (
  select coalesce((t.settings->'thresholds'->>'downtime_cost_per_hour')::numeric, 0) as per_hour
    from public.tenants t where t.id = p_tenant
),
first_install as (
  select distinct on (e.part_item_id) e.part_item_id, e.asset_id, e.occurred_at
    from public.part_events e
   where e.tenant_id = p_tenant and e.event_type = 'installed' and e.asset_id is not null
   order by e.part_item_id, e.occurred_at, e.id
),
part_buy as (
  select fi.asset_id, sum(pi.purchase_cost) as cost
    from first_install fi
    join public.part_items pi on pi.id = fi.part_item_id
   where fi.occurred_at >= p_from and fi.occurred_at <= p_to
   group by fi.asset_id
),
part_extra as (
  select coalesce(e.asset_id, li.asset_id) as asset_id, sum(e.cost) as cost
    from public.part_events e
    left join lateral (
      select x.asset_id
        from public.part_events x
       where x.part_item_id = e.part_item_id and x.event_type = 'installed' and x.asset_id is not null
         and x.occurred_at <= e.occurred_at
       order by x.occurred_at desc, x.id desc limit 1
    ) li on true
   where e.tenant_id = p_tenant and e.cost is not null and e.occurred_at >= p_from and e.occurred_at <= p_to
   group by 1
),
consum as (
  select sm.asset_id, sum(-sm.qty * coalesce(sm.unit_cost, 0)) as cost
    from public.stock_movements sm
   where sm.tenant_id = p_tenant and sm.kind = 'out' and sm.asset_id is not null
     and sm.occurred_at >= p_from and sm.occurred_at <= p_to
   group by sm.asset_id
),
wo as (
  select w.asset_id,
         count(*) filter (where w.status = 'done' and w.kind = 'planned' and w.completed_at >= p_from and w.completed_at <= p_to) as planned_done,
         count(*) filter (where w.kind = 'breakdown' and w.created_at <= p_to
                            and coalesce(w.down_to, w.completed_at, now()) >= p_from) as breakdowns,
         sum(w.labor_cost)    filter (where w.status = 'done' and w.completed_at >= p_from and w.completed_at <= p_to) as labor_cost,
         sum(w.external_cost) filter (where w.status = 'done' and w.completed_at >= p_from and w.completed_at <= p_to) as external_cost,
         sum(greatest(extract(epoch from least(coalesce(w.down_to, now()), p_to) - greatest(w.down_from, p_from)), 0) / 60)
           filter (where w.kind = 'breakdown' and w.down_from is not null) as downtime_minutes
    from public.work_orders w
   where w.tenant_id = p_tenant and w.status <> 'cancelled'
   group by w.asset_id
),
readings as (
  select mr.asset_id, mr.read_at as at, mr.hours
    from public.meter_readings mr where mr.tenant_id = p_tenant and mr.hours is not null
  union all
  select i.asset_id, i.completed_at, i.asset_hours
    from public.inspections i where i.tenant_id = p_tenant and i.status = 'completed' and i.asset_hours is not null
  union all
  select w.asset_id, w.completed_at, w.asset_hours_at_done
    from public.work_orders w where w.tenant_id = p_tenant and w.status = 'done' and w.asset_hours_at_done is not null
  union all
  select a.id, now(), a.meter_hours from public.assets a where a.tenant_id = p_tenant
),
-- r0: dönem başından önceki son okuma, r1: dönem içindeki ilk okuma. İkisi de varsa
-- dönem başındaki saat aradaki doğrudan (interpolasyon) bulunur.
hrs as (
  select a.id as asset_id,
         round(e.hours - case when r0.at is null then r1.hours
                              when r1.at is null then r0.hours
                              else r0.hours + (r1.hours - r0.hours)
                                   * extract(epoch from p_from - r0.at) / extract(epoch from r1.at - r0.at) end, 1) as hours_worked,
         case when r0.at is not null then p_from else r1.at end as hours_from
    from public.assets a
    left join lateral (
      select r.at, r.hours from readings r where r.asset_id = a.id and r.at <= p_from order by r.at desc, r.hours desc limit 1
    ) r0 on true
    left join lateral (
      select r.at, r.hours from readings r where r.asset_id = a.id and r.at > p_from and r.at <= p_to order by r.at, r.hours limit 1
    ) r1 on true
    left join lateral (
      select max(r.hours) as hours from readings r where r.asset_id = a.id and r.at <= p_to
    ) e on true
   where a.tenant_id = p_tenant
),
c as (
  select a.id as asset_id, a.code as asset_code, a.status as asset_status, a.site_id, s.name as site_name,
         am.manufacturer || ' ' || am.model as model_name,
         round(coalesce(pb.cost, 0) + coalesce(pe.cost, 0), 2) as parts_cost,
         round(coalesce(cs.cost, 0), 2) as consumables_cost,
         coalesce(wo.labor_cost, 0) as labor_cost,
         coalesce(wo.external_cost, 0) as external_cost,
         coalesce(round(wo.downtime_minutes), 0)::integer as downtime_minutes,
         round(coalesce(wo.downtime_minutes, 0) / 60 * coalesce(a.downtime_cost_per_hour, rate.per_hour), 2) as downtime_cost,
         coalesce(wo.planned_done, 0)::integer as planned_done,
         coalesce(wo.breakdowns, 0)::integer as breakdowns,
         greatest(coalesce(h.hours_worked, 0), 0) as hours_worked, h.hours_from,
         coalesce(a.downtime_cost_per_hour, rate.per_hour) as downtime_rate,
         a.downtime_cost_per_hour is not null as downtime_rate_own
    from public.assets a
    cross join rate
    left join public.sites s on s.id = a.site_id
    left join public.asset_models am on am.id = a.model_id
    left join part_buy pb on pb.asset_id = a.id
    left join part_extra pe on pe.asset_id = a.id
    left join consum cs on cs.asset_id = a.id
    left join wo on wo.asset_id = a.id
    left join hrs h on h.asset_id = a.id
   where a.tenant_id = p_tenant
)
select c.asset_id, c.asset_code, c.asset_status, c.site_id, c.site_name, c.model_name,
       c.parts_cost, c.consumables_cost, c.labor_cost, c.external_cost, c.downtime_minutes, c.downtime_cost,
       c.parts_cost + c.consumables_cost + c.labor_cost + c.external_cost + c.downtime_cost as total,
       c.planned_done, c.breakdowns, c.hours_worked, c.hours_from,
       case when c.hours_worked > 0
            then round((c.parts_cost + c.consumables_cost + c.labor_cost + c.external_cost + c.downtime_cost) / c.hours_worked, 2) end
         as cost_per_hour,
       c.downtime_rate, c.downtime_rate_own
  from c;
$$;

grant execute on function public.asset_tco(uuid, timestamptz, timestamptz) to sparetwin_app;
