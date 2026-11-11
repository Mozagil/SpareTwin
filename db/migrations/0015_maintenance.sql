-- =====================================================================
-- SpareTwin — 0015: Bakım planları ve iş emirleri (Faz 2)
-- ---------------------------------------------------------------------
-- Bakım planı: saat (interval_hours) ve/veya takvim (interval_days) bazlı
-- periyodik bakım; tek makineye ya da bir makine modelinin tüm makinelerine
-- bağlanır. Planın sarf listesi (filtre 4 adet, yağ 60 litre) vardır.
--
-- İş emri: planlı bakım ya da arıza. Arıza emri açık olduğu sürece makine
-- 'down', planlı emir sürerken 'maintenance' durumundadır; emir kapanınca
-- makine kendiliğinden 'active' olur (asset_refresh_status). Duruş süresi
-- down_from → down_to farkıdır.
--
-- Emir tamamlanınca sarf kalemleri stok defterinden düşer (stock_move 'out',
-- makineye kullanım, referans = emir no). Ayrı bir "bakımda kullanılan"
-- sayacı yok: K-013 ile aynı kapı. Makine saati girildiyse sayaç da güncellenir.
--
-- Sıradaki bakım (v_maintenance_due): son tamamlanan emrin saati/tarihi +
-- periyot; hiç yapılmamışsa saat için bir sonraki periyot katı, takvim için
-- plan tarihi + periyot. Firmanın "yaklaşıyor" eşiği (maint_warn_hours 50,
-- maint_warn_days 7) tenants.settings->'thresholds' içinden okunur.
-- =====================================================================

create type app.wo_kind   as enum ('planned', 'breakdown');
create type app.wo_status as enum ('open', 'in_progress', 'done', 'cancelled');

-- ---------- Bakım planı ----------
create table public.maintenance_plans (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references public.tenants(id) on delete cascade,
  name            text not null check (length(name) between 2 and 120),
  asset_id        uuid references public.assets(id) on delete cascade,        -- tek makine
  model_id        uuid references public.asset_models(id) on delete cascade,  -- ya da modelin tüm makineleri
  interval_hours  numeric(10,1) check (interval_hours > 0),
  interval_days   integer check (interval_days > 0),
  checklist       jsonb not null default '[]'::jsonb,   -- ["Hidrolik filtre değişimi", ...]
  notes           text,
  is_active       boolean not null default true,
  created_by      uuid references public.app_users(id) on delete set null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint plan_scope check ((asset_id is null) <> (model_id is null)),
  constraint plan_interval check (interval_hours is not null or interval_days is not null)
);
create index on public.maintenance_plans (tenant_id, is_active);
create trigger trg_maintenance_plans_updated before update on public.maintenance_plans
  for each row execute function app.touch_updated_at();

create table public.maintenance_plan_parts (
  id         bigint generated always as identity primary key,
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  plan_id    uuid not null references public.maintenance_plans(id) on delete cascade,
  part_id    uuid not null references public.parts(id),
  qty        numeric(12,3) not null check (qty > 0),
  unique (plan_id, part_id)
);

-- ---------- İş emri ----------
create table public.work_orders (
  id                   uuid primary key default gen_random_uuid(),
  tenant_id            uuid not null references public.tenants(id) on delete cascade,
  number               text not null,                                       -- BK-2026-0001
  asset_id             uuid not null references public.assets(id) on delete cascade,
  plan_id              uuid references public.maintenance_plans(id) on delete set null,
  kind                 app.wo_kind not null default 'planned',
  status               app.wo_status not null default 'open',
  title                text not null check (length(title) between 2 and 160),
  description          text,
  due_at               date,                 -- planlı: hedef tarih
  due_hours            numeric(10,1),        -- planlı: hedef makine saati
  down_from            timestamptz,          -- arıza: makine ne zaman durdu
  down_to              timestamptz,          -- arıza: ne zaman çalışmaya döndü
  downtime_minutes     integer generated always as ((extract(epoch from (down_to - down_from)) / 60)::integer) stored,
  reason_code          text,                 -- arıza sebebi: hydraulic, electrical, engine, tire, transmission, structural, operator, other
  part_item_id         uuid references public.part_items(id) on delete set null,  -- ilgili parça
  asset_hours_at_done  numeric(10,1),
  labor_cost           numeric(12,2) check (labor_cost >= 0),
  external_cost        numeric(12,2) check (external_cost >= 0),   -- dış servis, nakliye
  created_by           uuid references public.app_users(id) on delete set null,
  assigned_to          uuid references public.app_users(id) on delete set null,
  completed_by         uuid references public.app_users(id) on delete set null,
  started_at           timestamptz,
  completed_at         timestamptz,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  unique (tenant_id, number),
  constraint wo_downtime check (down_to is null or down_from is null or down_to >= down_from)
);
create index on public.work_orders (tenant_id, status);
create index on public.work_orders (asset_id, status);
create index on public.work_orders (plan_id, asset_id, status);
create trigger trg_work_orders_updated before update on public.work_orders
  for each row execute function app.touch_updated_at();

create table public.work_order_parts (
  id             bigint generated always as identity primary key,
  tenant_id      uuid not null references public.tenants(id) on delete cascade,
  work_order_id  uuid not null references public.work_orders(id) on delete cascade,
  part_id        uuid not null references public.parts(id),
  qty            numeric(12,3) not null check (qty > 0),
  site_id        uuid references public.sites(id) on delete set null,   -- hangi depodan düşer
  unit_cost      numeric(12,4),                                          -- tamamlanınca defterden gelir
  unique (work_order_id, part_id)
);

alter table public.maintenance_plans enable row level security;
alter table public.maintenance_plan_parts enable row level security;
alter table public.work_orders enable row level security;
alter table public.work_order_parts enable row level security;
grant select, insert, update on public.maintenance_plans to sparetwin_app;
grant select, insert, update, delete on public.maintenance_plan_parts to sparetwin_app;
grant select, insert, update on public.work_orders to sparetwin_app;
grant select, insert, update, delete on public.work_order_parts to sparetwin_app;

create policy mp_select on public.maintenance_plans for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy mp_insert on public.maintenance_plans for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager}'));
create policy mp_update on public.maintenance_plans for update to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager}'));
create policy mpp_select on public.maintenance_plan_parts for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy mpp_write on public.maintenance_plan_parts for all to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager}'))
  with check (app.has_role(tenant_id, '{owner,admin,manager}'));
create policy wo_select on public.work_orders for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy wo_insert on public.work_orders for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager,technician}'));
create policy wo_update on public.work_orders for update to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager,technician}'));
create policy wop_select on public.work_order_parts for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy wop_write on public.work_order_parts for all to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager,technician}'))
  with check (app.has_role(tenant_id, '{owner,admin,manager,technician}'));

-- ---------- Emir numarası: BK-<yıl>-<sıra>, firma içinde ----------
create or replace function app.next_wo_number(p_tenant uuid)
returns text language plpgsql volatile
set search_path = public, app
as $$
declare
  y text := to_char(now(), 'YYYY');
  n integer;
begin
  perform pg_advisory_xact_lock(hashtextextended('wo:' || p_tenant::text, 0));
  select coalesce(max(split_part(number, '-', 3)::integer), 0) + 1 into n
    from public.work_orders
   where tenant_id = p_tenant and number ~ ('^BK-' || y || '-[0-9]+$');
  return 'BK-' || y || '-' || lpad(n::text, 4, '0');
end $$;
grant execute on function app.next_wo_number(uuid) to sparetwin_app;

-- ---------- Makine durumu iş emirlerinden türer ----------
-- Açık arıza emri varsa 'down', süren planlı emir varsa 'maintenance', yoksa 'active'.
-- 'retired' makineye dokunulmaz.
create or replace function app.asset_refresh_status(p_asset uuid)
returns void language plpgsql
set search_path = public, app
as $$
declare
  cur app.asset_status;
  nxt app.asset_status;
begin
  select status into cur from public.assets where id = p_asset for update;
  if not found or cur = 'retired' then return; end if;
  if exists (select 1 from public.work_orders
              where asset_id = p_asset and kind = 'breakdown' and status in ('open', 'in_progress')) then
    nxt := 'down';
  elsif exists (select 1 from public.work_orders
                 where asset_id = p_asset and status = 'in_progress') then
    nxt := 'maintenance';
  elsif cur in ('down', 'maintenance') then
    nxt := 'active';   -- emir kalmadı: makine çalışmaya döner
  else
    return;
  end if;
  if nxt <> cur then
    update public.assets set status = nxt where id = p_asset;
  end if;
end $$;
grant execute on function app.asset_refresh_status(uuid) to sparetwin_app;

create or replace function app.work_orders_asset_status_trg()
returns trigger language plpgsql
set search_path = public, app
as $$
begin
  perform app.asset_refresh_status(new.asset_id);
  return new;
end $$;
create trigger trg_work_orders_asset_status
  after insert or update of status, kind on public.work_orders
  for each row execute function app.work_orders_asset_status_trg();

-- ---------- Durum geçişleri (kurallar tek yerde) ----------
-- open → in_progress → done; open | in_progress → cancelled.
-- Tamamlanırken: sarf kalemleri stoktan düşer, makine saati (verildiyse) sayaca yazılır,
-- arızada duruş bitişi kaydedilir.
create or replace function public.wo_set_status(
  p_wo uuid, p_status text, p_asset_hours numeric default null, p_down_to timestamptz default null
) returns public.work_orders
language plpgsql security invoker
set search_path = public, app
as $$
declare
  w   public.work_orders;
  a   public.assets;
  wp  record;
  mv  public.stock_movements;
begin
  select * into w from public.work_orders where id = p_wo for update;
  if not found then raise exception 'İş emri bulunamadı' using errcode = 'P0002'; end if;

  if p_status = 'in_progress' then
    if w.status <> 'open' then
      raise exception 'Yalnızca açık emir başlatılabilir' using errcode = '22023';
    end if;
    update public.work_orders set status = 'in_progress', started_at = now() where id = p_wo returning * into w;

  elsif p_status = 'done' then
    if w.status not in ('open', 'in_progress') then
      raise exception 'Kapanmış emir yeniden tamamlanamaz' using errcode = '22023';
    end if;
    select * into a from public.assets where id = w.asset_id;
    if p_asset_hours is not null and p_asset_hours > a.meter_hours then
      a := public.record_meter_reading(w.asset_id, p_asset_hours, null, 'manual');
    end if;
    if w.kind = 'breakdown' and w.down_from is not null and coalesce(p_down_to, w.down_to, now()) < w.down_from then
      raise exception 'Çalışmaya dönüş, duruş başlangıcından önce olamaz' using errcode = '22023';
    end if;
    -- Sarf kalemleri: stok defterinden makineye kullanım olarak düşer
    for wp in select * from public.work_order_parts where work_order_id = p_wo order by id loop
      mv := public.stock_move(wp.part_id, wp.site_id, 'out', wp.qty, null, w.asset_id,
                              case when w.kind = 'breakdown' then 'arıza onarımı' else 'periyodik bakım' end,
                              w.number, w.title, null, w.tenant_id);
      update public.work_order_parts set unit_cost = mv.unit_cost where id = wp.id;
    end loop;
    update public.work_orders
       set status = 'done', completed_at = now(), completed_by = app.current_user_id(),
           started_at = coalesce(started_at, now()),
           asset_hours_at_done = coalesce(p_asset_hours, a.meter_hours),
           down_to = case when kind = 'breakdown' then coalesce(p_down_to, down_to, now()) else down_to end
     where id = p_wo returning * into w;

  elsif p_status = 'cancelled' then
    if w.status not in ('open', 'in_progress') then
      raise exception 'Kapanmış emir iptal edilemez' using errcode = '22023';
    end if;
    update public.work_orders set status = 'cancelled', completed_at = now(), completed_by = app.current_user_id()
     where id = p_wo returning * into w;
  else
    raise exception 'Geçersiz durum: %', p_status using errcode = '22023';
  end if;
  return w;
end $$;
grant execute on function public.wo_set_status(uuid, text, numeric, timestamptz) to sparetwin_app;

-- ---------- Sıradaki bakımlar ----------
-- Plan × makine çifti başına bir satır. hours_per_day son 60 günün sayaç okumalarından;
-- varsa saat bazlı bakım için tahmini tarih (eta_at) verir.
create or replace view public.v_maintenance_due
with (security_invoker = true) as
with pa as (
  select p.id as plan_id, p.tenant_id, p.name, p.interval_hours, p.interval_days, p.checklist, p.created_at as plan_created_at,
         a.id as asset_id, a.code as asset_code, a.meter_hours, a.status as asset_status, a.site_id,
         coalesce((t.settings->'thresholds'->>'maint_warn_hours')::numeric, 50) as warn_hours,
         coalesce((t.settings->'thresholds'->>'maint_warn_days')::integer, 7) as warn_days
    from public.maintenance_plans p
    join public.tenants t on t.id = p.tenant_id
    join public.assets a on a.tenant_id = p.tenant_id and a.status <> 'retired'
         and (a.id = p.asset_id or (p.model_id is not null and a.model_id = p.model_id))
   where p.is_active
),
calc as (
  select pa.*,
         ld.completed_at as last_done_at, ld.asset_hours_at_done as last_done_hours, ld.number as last_done_number,
         ow.id as open_work_order_id, ow.number as open_work_order_number, ow.status as open_work_order_status,
         case when pa.interval_hours is not null then
           coalesce(ld.asset_hours_at_done + pa.interval_hours,
                    (floor(pa.meter_hours / pa.interval_hours) + 1) * pa.interval_hours) end as next_due_hours,
         case when pa.interval_days is not null then
           coalesce(ld.completed_at::date, pa.plan_created_at::date) + pa.interval_days end as next_due_at,
         rt.hours_per_day
    from pa
    left join lateral (
      select w.completed_at, w.asset_hours_at_done, w.number
        from public.work_orders w
       where w.plan_id = pa.plan_id and w.asset_id = pa.asset_id and w.status = 'done'
       order by w.completed_at desc limit 1
    ) ld on true
    left join lateral (
      select w.id, w.number, w.status
        from public.work_orders w
       where w.plan_id = pa.plan_id and w.asset_id = pa.asset_id and w.status in ('open', 'in_progress')
       order by w.created_at limit 1
    ) ow on true
    left join lateral (
      select case when count(*) >= 2 and max(read_at) > min(read_at)
                  then round((max(hours) - min(hours)) / greatest(extract(epoch from (max(read_at) - min(read_at))) / 86400, 1), 1) end as hours_per_day
        from public.meter_readings mr
       where mr.asset_id = pa.asset_id and mr.hours is not null and mr.read_at > now() - interval '60 days'
    ) rt on true
)
select c.plan_id, c.tenant_id, c.name, c.interval_hours, c.interval_days, c.checklist,
       c.asset_id, c.asset_code, c.meter_hours, c.asset_status, c.site_id,
       c.last_done_at, c.last_done_hours, c.last_done_number,
       c.next_due_hours, c.next_due_at,
       c.next_due_hours - c.meter_hours as hours_left,
       c.next_due_at - current_date as days_left,
       c.hours_per_day,
       case when c.hours_per_day > 0 and c.next_due_hours is not null
            then least(current_date + ceil(greatest(c.next_due_hours - c.meter_hours, 0) / c.hours_per_day)::integer, c.next_due_at)
            else c.next_due_at end as eta_at,
       case when c.next_due_hours - c.meter_hours < 0 or c.next_due_at < current_date then 'overdue'
            when c.next_due_hours - c.meter_hours <= c.warn_hours or c.next_due_at - current_date <= c.warn_days then 'due_soon'
            else 'ok' end as state,
       c.open_work_order_id, c.open_work_order_number, c.open_work_order_status
  from calc c;

grant select on public.v_maintenance_due to sparetwin_app;

-- ---------- Makine başına bakım özeti (son 12 ay) ----------
-- Parça + işçilik + dış servis maliyeti ve duruş: toplam sahip olma maliyetinin bakım ayağı.
create or replace view public.v_asset_maintenance
with (security_invoker = true) as
select a.id as asset_id, a.tenant_id, a.code as asset_code,
       count(w.id) filter (where w.status = 'done' and w.kind = 'planned')   as planned_done,
       count(w.id) filter (where w.status = 'done' and w.kind = 'breakdown') as breakdowns,
       count(w.id) filter (where w.status in ('open', 'in_progress'))        as open_orders,
       coalesce(sum(w.downtime_minutes) filter (where w.status = 'done'), 0) as downtime_minutes,
       coalesce(sum(coalesce(w.labor_cost, 0) + coalesce(w.external_cost, 0)) filter (where w.status = 'done'), 0)
         + coalesce((select sum(wp.qty * coalesce(wp.unit_cost, 0))
                       from public.work_order_parts wp join public.work_orders w2 on w2.id = wp.work_order_id
                      where w2.asset_id = a.id and w2.status = 'done' and w2.completed_at > now() - interval '12 months'), 0)
         as cost_12m,
       max(w.completed_at) filter (where w.status = 'done') as last_done_at
  from public.assets a
  left join public.work_orders w on w.asset_id = a.id and (w.completed_at is null or w.completed_at > now() - interval '12 months')
 group by a.id, a.tenant_id, a.code;

grant select on public.v_asset_maintenance to sparetwin_app;
