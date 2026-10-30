-- =====================================================================
-- SpareTwin — TireIQ modülü (lastik & jant) + ortak kütüphane
-- ---------------------------------------------------------------------
-- TireIQ, çekirdek ikiz motorunun üzerine kurulan ilk dikey pakettir.
-- Lastik, çekirdekte sadece bir parça kategorisidir; lastiğe özgü
-- bilgiler aşağıdaki uzantı tablolarında durur. Aynı desen ileride
-- hidrolik, şanzıman, zincir vb. için tekrar kullanılır.
-- =====================================================================

create table public.tire_specs (
  part_id          uuid primary key references public.parts(id) on delete cascade,
  size             text not null,                 -- '29.5R25', '18.00-25'
  construction     text not null check (construction in ('radial', 'bias', 'solid')),
  rating           text,                          -- '2*', '28PR'
  tra_code         text,                          -- 'L-5', 'E-4'
  otd_mm           numeric(6,1) not null,         -- orijinal diş derinliği
  scrap_tread_mm   numeric(6,1) not null default 0 -- bu derinliğe inince söküm/kaplama
    check (scrap_tread_mm >= 0),
  retreadable      boolean not null default true,
  check (otd_mm > scrap_tread_mm)
);

create table public.rim_specs (
  part_id             uuid primary key references public.parts(id) on delete cascade,
  size                text not null,               -- '25x25.00/3.5'
  pieces              smallint check (pieces between 1 and 7),
  max_pressure_kpa    numeric(7,1),
  ndt_interval_hours  numeric(8,1)                 -- tahribatsız muayene periyodu (uyumluluk)
);

alter table public.tire_specs enable row level security;
alter table public.rim_specs  enable row level security;
grant select, insert, update, delete on public.tire_specs, public.rim_specs to sparetwin_app;

create policy tire_specs_select on public.tire_specs for select to sparetwin_app
  using (exists (select 1 from public.parts p where p.id = part_id
                 and (p.tenant_id is null or app.is_member(p.tenant_id))));
create policy tire_specs_write on public.tire_specs for all to sparetwin_app
  using (exists (select 1 from public.parts p where p.id = part_id and p.tenant_id is not null
                 and app.has_role(p.tenant_id, '{owner,admin,manager}')))
  with check (exists (select 1 from public.parts p where p.id = part_id and p.tenant_id is not null
                 and app.has_role(p.tenant_id, '{owner,admin,manager}')));

create policy rim_specs_select on public.rim_specs for select to sparetwin_app
  using (exists (select 1 from public.parts p where p.id = part_id
                 and (p.tenant_id is null or app.is_member(p.tenant_id))));
create policy rim_specs_write on public.rim_specs for all to sparetwin_app
  using (exists (select 1 from public.parts p where p.id = part_id and p.tenant_id is not null
                 and app.has_role(p.tenant_id, '{owner,admin,manager}')))
  with check (exists (select 1 from public.parts p where p.id = part_id and p.tenant_id is not null
                 and app.has_role(p.tenant_id, '{owner,admin,manager}')));

-- ---------- Ortak kütüphane: parça kategorileri ----------------------
insert into public.part_categories (tenant_id, code, name, is_serialized, measurement_profile, required_photo_angles) values
  (null, 'tire', 'Lastik', true,
   '[{"metric":"tread_depth_mm","label":"Diş derinliği","unit":"mm","required":true,"min":0,"max":200},
     {"metric":"pressure_kpa","label":"Basınç","unit":"kPa","required":false,"min":100,"max":1200}]',
   '{tread,sidewall}'),
  (null, 'rim', 'Jant', true,
   '[{"metric":"visual_ok","label":"Görsel kontrol (1=uygun, 0=hasarlı)","unit":"","required":false,"min":0,"max":1}]',
   '{}'),
  (null, 'hyd_cylinder', 'Hidrolik silindir', true,
   '[{"metric":"drift_mm","label":"10 dk çökme","unit":"mm","required":false,"min":0,"max":100}]',
   '{}'),
  (null, 'hyd_pump', 'Hidrolik pompa', true, '[]', '{}'),
  (null, 'battery', 'Akü', true,
   '[{"metric":"voltage_v","label":"Gerilim","unit":"V","required":false,"min":0,"max":100}]', '{}'),
  (null, 'filter', 'Filtre', false, '[]', '{}');

-- ---------- Ortak kütüphane: pozisyon şablonları ---------------------
-- x/y değerleri dashboard'daki üstten görünüş şemasında 0–100 konumdur.
with t as (
  insert into public.position_templates (tenant_id, name, layout)
  values (null, 'Lastikli yükleyici (4 lastik + hidrolik)', 'loader')
  returning id
)
insert into public.template_positions (template_id, code, label, category_code, axle, x, y, sort_order)
select t.id, v.code, v.label, v.cat, v.axle, v.x, v.y, v.ord from t, (values
  ('A1-L',        'Ön aks sol',            'tire',         1, 22, 30, 1),
  ('A1-R',        'Ön aks sağ',            'tire',         1, 22, 70, 2),
  ('A2-L',        'Arka aks sol',          'tire',         2, 74, 30, 3),
  ('A2-R',        'Arka aks sağ',          'tire',         2, 74, 70, 4),
  ('LIFT-CYL-L',  'Kaldırma silindiri sol','hyd_cylinder', null, 10, 40, 10),
  ('LIFT-CYL-R',  'Kaldırma silindiri sağ','hyd_cylinder', null, 10, 60, 11),
  ('TILT-CYL',    'Kepçe devirme silindiri','hyd_cylinder', null, 6, 50, 12),
  ('MAIN-PUMP',   'Ana hidrolik pompa',    'hyd_pump',     null, 58, 50, 13)
) as v(code, label, cat, axle, x, y, ord);

with t as (
  insert into public.position_templates (tenant_id, name, layout)
  values (null, 'Reach stacker (ön çift, arka tek)', 'reach_stacker')
  returning id
)
insert into public.template_positions (template_id, code, label, category_code, axle, x, y, sort_order)
select t.id, v.code, v.label, v.cat, v.axle, v.x, v.y, v.ord from t, (values
  ('A1-LO', 'Ön aks sol dış',  'tire', 1, 24, 18, 1),
  ('A1-LI', 'Ön aks sol iç',   'tire', 1, 24, 32, 2),
  ('A1-RI', 'Ön aks sağ iç',   'tire', 1, 24, 68, 3),
  ('A1-RO', 'Ön aks sağ dış',  'tire', 1, 24, 82, 4),
  ('A2-L',  'Arka aks sol',    'tire', 2, 80, 28, 5),
  ('A2-R',  'Arka aks sağ',    'tire', 2, 80, 72, 6),
  ('BOOM-CYL', 'Bom kaldırma silindiri', 'hyd_cylinder', null, 46, 50, 10)
) as v(code, label, cat, axle, x, y, ord);

with t as (
  insert into public.position_templates (tenant_id, name, layout)
  values (null, 'Forklift (4 lastik)', 'forklift')
  returning id
)
insert into public.template_positions (template_id, code, label, category_code, axle, x, y, sort_order)
select t.id, v.code, v.label, v.cat, v.axle, v.x, v.y, v.ord from t, (values
  ('A1-L',  'Ön aks sol',   'tire', 1, 28, 26, 1),
  ('A1-R',  'Ön aks sağ',   'tire', 1, 28, 74, 2),
  ('A2-L',  'Arka aks sol', 'tire', 2, 76, 30, 3),
  ('A2-R',  'Arka aks sağ', 'tire', 2, 76, 70, 4),
  ('MAST-CYL', 'Direk kaldırma silindiri', 'hyd_cylinder', null, 10, 50, 10),
  ('BATTERY',  'Akü',        'battery', null, 56, 50, 11)
) as v(code, label, cat, axle, x, y, ord);

-- ---------- Görünüm: lastik sağlığı ----------------------------------
create or replace view public.v_tire_health
with (security_invoker = true) as
select
  l.*,
  ts.size,
  ts.construction,
  ts.otd_mm,
  ts.scrap_tread_mm,
  (l.latest_measurements->'tread_depth_mm'->>'value')::numeric as tread_mm,
  (l.latest_measurements->'pressure_kpa'->>'value')::numeric   as pressure_kpa,
  -- Kalan diş yüzdesi: hurda sınırına göre
  round(100 * greatest(
    ((l.latest_measurements->'tread_depth_mm'->>'value')::numeric - ts.scrap_tread_mm)
      / (ts.otd_mm - ts.scrap_tread_mm), 0), 1)                 as tread_remaining_pct,
  -- Aşınma hızı (mm/saat) ve tahmini kalan saat (doğrusal model, Faz 1)
  case when l.hours_total > 0 then
    round((ts.otd_mm - (l.latest_measurements->'tread_depth_mm'->>'value')::numeric) / l.hours_total, 5)
  end                                                           as wear_mm_per_hour,
  case when l.hours_total > 0
        and ts.otd_mm > (l.latest_measurements->'tread_depth_mm'->>'value')::numeric then
    round(greatest((l.latest_measurements->'tread_depth_mm'->>'value')::numeric - ts.scrap_tread_mm, 0)
          / ((ts.otd_mm - (l.latest_measurements->'tread_depth_mm'->>'value')::numeric) / l.hours_total))
  end                                                           as projected_hours_left,
  case when l.hours_total > 0 then round(l.cost_total / l.hours_total, 2) end as cost_per_hour,
  -- Ömür sonunda beklenen saat başı maliyet: maliyet ÷ (çalışılan + tahmini kalan saat)
  case when l.hours_total > 0 and w.rate > 0 then
    round(l.cost_total / (l.hours_total + greatest(w.cur - ts.scrap_tread_mm, 0) / w.rate), 2)
  end                                                           as expected_cost_per_hour
from public.v_part_items_live l
join public.tire_specs ts on ts.part_id = l.part_id
cross join lateral (
  select (l.latest_measurements->'tread_depth_mm'->>'value')::numeric as cur,
         case when l.hours_total > 0
              then (ts.otd_mm - (l.latest_measurements->'tread_depth_mm'->>'value')::numeric) / l.hours_total
         end as rate
) w
where l.category_code = 'tire';

-- ---------- Görünüm: jant uyumluluğu (NDT periyodu) ------------------
create or replace view public.v_rim_compliance
with (security_invoker = true) as
select
  l.id, l.tenant_id, l.serial_no, l.asset_code, l.current_position, l.hours_total,
  rs.ndt_interval_hours,
  ndt.last_ndt_hours,
  l.hours_total - coalesce(ndt.last_ndt_hours, 0) as hours_since_ndt,
  case
    when rs.ndt_interval_hours is null then 'not_required'
    when l.hours_total - coalesce(ndt.last_ndt_hours, 0) > rs.ndt_interval_hours then 'overdue'
    when l.hours_total - coalesce(ndt.last_ndt_hours, 0) > rs.ndt_interval_hours * 0.9 then 'due_soon'
    else 'ok'
  end as compliance
from public.v_part_items_live l
join public.rim_specs rs on rs.part_id = l.part_id
left join lateral (
  -- NDT muayenesi log_part_event(item, 'inspected', 'ndt') ile kaydedilir.
  select max(e.part_hours) as last_ndt_hours
    from public.part_events e
   where e.part_item_id = l.id and e.event_type = 'inspected' and e.reason_code = 'ndt'
) ndt on true
where l.category_code = 'rim';

-- ---------- Görünüm: tüm parçalar için ortak sağlık skoru ------------
-- Lastikte diş derinliği, diğer parçalarda beklenen ömre göre kullanım.
create or replace view public.v_part_health
with (security_invoker = true) as
select
  l.id, l.tenant_id, l.current_asset_id, l.asset_code, l.current_position,
  l.category_code, l.part_name, l.serial_no, l.status, l.hours_total,
  coalesce(
    th.tread_remaining_pct,
    case when l.expected_life_hours > 0
         then round(greatest(100 * (1 - l.hours_total / l.expected_life_hours), 0), 1) end
  ) as condition_pct,
  case
    when coalesce(th.tread_remaining_pct,
                  100 * (1 - l.hours_total / nullif(l.expected_life_hours, 0))) is null then 'unknown'
    when coalesce(th.tread_remaining_pct,
                  100 * (1 - l.hours_total / nullif(l.expected_life_hours, 0))) < 20 then 'critical'
    when coalesce(th.tread_remaining_pct,
                  100 * (1 - l.hours_total / nullif(l.expected_life_hours, 0))) < 40 then 'watch'
    else 'ok'
  end as band,
  th.projected_hours_left
from public.v_part_items_live l
left join public.v_tire_health th on th.id = l.id;

-- ---------- Görünüm: makine bazlı özet (filo şeridi) -----------------
create or replace view public.v_asset_health
with (security_invoker = true) as
select
  a.id, a.tenant_id, a.code, a.status, a.meter_hours, a.site_id,
  am.manufacturer, am.model, am.category, pt.layout,
  count(ph.id)                                   as installed_parts,
  count(*) filter (where ph.band = 'critical')   as critical_parts,
  count(*) filter (where ph.band = 'watch')      as watch_parts,
  min(ph.condition_pct)                          as worst_condition_pct,
  (select max(i.completed_at) from public.inspections i
    where i.asset_id = a.id and i.status = 'completed') as last_inspection_at
from public.assets a
left join public.asset_models am       on am.id = a.model_id
left join public.position_templates pt on pt.id = am.template_id
left join public.v_part_health ph      on ph.current_asset_id = a.id and ph.status = 'installed'
group by a.id, am.manufacturer, am.model, am.category, pt.layout;

grant select on public.v_part_items_live, public.v_tire_health, public.v_rim_compliance,
                public.v_part_health, public.v_asset_health to sparetwin_app;
