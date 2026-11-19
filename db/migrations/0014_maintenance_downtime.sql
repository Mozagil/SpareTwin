-- =====================================================================
-- SpareTwin — 0014: Bakım planları, bakım kayıtları, arıza/duruş (Faz 2)
-- ---------------------------------------------------------------------
-- Bakım planı: makine başına periyodik iş (saat ve/veya takvim). "Yapıldı"
-- denince bakım kaydı açılır, plan sıfırlanır, malzemeler stoktan makineye
-- çıkılır (stock_move). Duruş: makinenin çalışmadığı süre, sebebi, maliyeti.
-- Toplam sahip olma maliyeti bu kayıtlardan ve stok/parça hareketlerinden okunur.
-- =====================================================================

create table public.maintenance_plans (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references public.tenants(id) on delete cascade,
  asset_id         uuid not null references public.assets(id) on delete cascade,
  name             text not null,
  interval_hours   numeric(10,1) check (interval_hours > 0),
  interval_days    int check (interval_days > 0),
  last_done_hours  numeric(10,1),
  last_done_at     timestamptz,
  materials        jsonb not null default '[]',   -- [{"part_id": "...", "qty": 2}]
  notes            text,
  active           boolean not null default true,
  created_at       timestamptz not null default now(),
  check (interval_hours is not null or interval_days is not null)
);
create index on public.maintenance_plans (tenant_id, asset_id);

create table public.maintenance_records (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenants(id) on delete cascade,
  asset_id     uuid not null references public.assets(id) on delete cascade,
  plan_id      uuid references public.maintenance_plans(id) on delete set null,
  title        text not null,
  asset_hours  numeric(10,1),
  labor_cost   numeric(12,2) check (labor_cost >= 0),
  notes        text,
  performed_by uuid references public.app_users(id),
  performed_at timestamptz not null default now()
);
create index on public.maintenance_records (asset_id, performed_at desc);

create type app.downtime_category as enum ('breakdown', 'planned_maintenance', 'tire', 'waiting_parts', 'operational', 'other');

create table public.downtime_events (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  asset_id      uuid not null references public.assets(id) on delete cascade,
  category      app.downtime_category not null,
  part_item_id  uuid references public.part_items(id) on delete set null,
  description   text,
  started_at    timestamptz not null default now(),
  ended_at      timestamptz,
  cost          numeric(12,2) check (cost >= 0),   -- tamir/servis bedeli
  created_by    uuid references public.app_users(id),
  created_at    timestamptz not null default now(),
  check (ended_at is null or ended_at >= started_at)
);
create index on public.downtime_events (asset_id, started_at desc);
-- Bir makinede aynı anda tek açık duruş
create unique index downtime_one_open on public.downtime_events (asset_id) where ended_at is null;

do $$
declare t text;
begin
  foreach t in array array['maintenance_plans', 'maintenance_records', 'downtime_events'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('grant select, insert, update on public.%I to sparetwin_app', t);
    execute format('create policy %1$s_select on public.%1$I for select to sparetwin_app using (app.is_member(tenant_id))', t);
    execute format('create policy %1$s_insert on public.%1$I for insert to sparetwin_app
                      with check (app.has_role(tenant_id, ''{owner,admin,manager,technician}''))', t);
    execute format('create policy %1$s_update on public.%1$I for update to sparetwin_app
                      using (app.has_role(tenant_id, ''{owner,admin,manager,technician}''))', t);
  end loop;
end $$;

-- ---------- Bakım durumu ----------
-- Yaklaşıyor: kalan ≤ %10 periyot (en az 50 saat) veya ≤ 7 gün. Geçmiş: kalan ≤ 0.
create or replace view public.v_maintenance_due
with (security_invoker = true) as
select mp.*, a.code as asset_code, a.meter_hours,
       mp.last_done_hours + mp.interval_hours                                   as next_due_hours,
       (mp.last_done_hours + mp.interval_hours) - a.meter_hours                 as hours_left,
       (mp.last_done_at + make_interval(days => mp.interval_days))              as next_due_at,
       extract(day from (mp.last_done_at + make_interval(days => mp.interval_days)) - now())::int as days_left,
       case
         when not mp.active then 'inactive'
         when (mp.interval_hours is not null and (mp.last_done_hours is null
                 or (mp.last_done_hours + mp.interval_hours) - a.meter_hours <= 0))
           or (mp.interval_days is not null and (mp.last_done_at is null
                 or mp.last_done_at + make_interval(days => mp.interval_days) <= now()))
           then 'overdue'
         when (mp.interval_hours is not null
                 and (mp.last_done_hours + mp.interval_hours) - a.meter_hours <= greatest(50, mp.interval_hours * 0.1))
           or (mp.interval_days is not null
                 and mp.last_done_at + make_interval(days => mp.interval_days) <= now() + interval '7 days')
           then 'due_soon'
         else 'ok'
       end as due_status
  from public.maintenance_plans mp
  join public.assets a on a.id = mp.asset_id;
grant select on public.v_maintenance_due to sparetwin_app;
