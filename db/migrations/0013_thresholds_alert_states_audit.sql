-- =====================================================================
-- SpareTwin — 0013: Firma eşikleri, uyarı durumu, denetim kaydı
-- ---------------------------------------------------------------------
-- TireIQ taslağından devralınan üç parça (bkz. docs/07-kararlar.md K-014):
--
-- 1) Eşikler firmaya göre ayarlanır. Şimdiye kadar koda gömülüydü:
--    kritik < %20, izleme < %40, jant "yaklaşıyor" > %90, kontrol aralığı
--    30 gün. Artık tenants.settings->'thresholds' içinden okunur; yoksa
--    aynı varsayılanlar geçerlidir, mevcut veri için hiçbir şey değişmez.
--      {"thresholds": {"critical_pct": 20, "watch_pct": 40,
--                      "rim_due_soon_pct": 90, "inspection_interval_days": 30}}
--    Görünümlerin kolonları aynı kaldığı için bağımlı görünümler ve API
--    etkilenmez.
--
-- 2) Uyarı durumu ekip bazlıdır: "üstlenildi" (biri ilgileniyor) veya
--    "gizlendi" (bu durum değişmeden tekrar gösterme). Bildirim anahtarı
--    durumu da içerdiği için (ör. part:<id>:critical:<ölçüm tarihi>)
--    durum kötüleşince anahtar değişir ve kayıt kendiliğinden düşer: %62'de
--    "gördüm" demek %85'i gizleyemez. Sorun geçince anahtar listeden çıkar,
--    kayıt API tarafından temizlenir. Okundu bilgisi (0011) kişisel kalır.
--
-- 3) Denetim kaydı: durum değiştiren her API isteği (kim, hangi firma, ne,
--    ne zaman, sonuç) sistem tarafından yazılır. Uygulama rolü bu tabloya
--    yazamaz, yalnızca firma yöneticileri okur. Faz 3'teki "denetim kaydı"
--    maddesi buraya çekildi.
-- =====================================================================

-- ---------- 1) Eşikler: görünümler firmanın ayarını okur ---------------
create or replace view public.v_part_health
with (security_invoker = true) as
select
  l.id, l.tenant_id, l.current_asset_id, l.asset_code, l.current_position,
  l.category_code, l.part_name, l.serial_no, l.status, l.hours_total,
  c.pct as condition_pct,
  case
    when c.pct is null then 'unknown'
    when c.pct < coalesce((t.settings->'thresholds'->>'critical_pct')::numeric, 20) then 'critical'
    when c.pct < coalesce((t.settings->'thresholds'->>'watch_pct')::numeric, 40)    then 'watch'
    else 'ok'
  end as band,
  th.projected_hours_left
from public.v_part_items_live l
left join public.v_tire_health th on th.id = l.id
left join public.tenants t on t.id = l.tenant_id
cross join lateral (
  -- Lastikte diş derinliği, diğer parçalarda beklenen ömre göre kullanım
  select coalesce(
    th.tread_remaining_pct,
    case when l.expected_life_hours > 0
         then round(greatest(100 * (1 - l.hours_total / l.expected_life_hours), 0), 1) end
  ) as pct
) c;

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
    when l.hours_total - coalesce(ndt.last_ndt_hours, 0)
         > rs.ndt_interval_hours * coalesce((t.settings->'thresholds'->>'rim_due_soon_pct')::numeric, 90) / 100
      then 'due_soon'
    else 'ok'
  end as compliance
from public.v_part_items_live l
join public.rim_specs rs on rs.part_id = l.part_id
left join public.tenants t on t.id = l.tenant_id
left join lateral (
  -- NDT muayenesi log_part_event(item, 'inspected', 'ndt') ile kaydedilir.
  select max(e.part_hours) as last_ndt_hours
    from public.part_events e
   where e.part_item_id = l.id and e.event_type = 'inspected' and e.reason_code = 'ndt'
) ndt on true
where l.category_code = 'rim';

-- ---------- 2) Uyarı durumu (ekip bazlı) --------------------------------
create table public.notification_states (
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  key        text not null,
  state      text not null check (state in ('acknowledged', 'dismissed')),
  note       text check (note is null or length(note) <= 500),
  user_id    uuid references public.app_users(id) on delete set null,
  at         timestamptz not null default now(),
  primary key (tenant_id, key)
);

alter table public.notification_states enable row level security;
grant select, insert, update, delete on public.notification_states to sparetwin_app;
create policy notification_states_select on public.notification_states for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy notification_states_write on public.notification_states for all to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager,technician}'))
  with check (app.has_role(tenant_id, '{owner,admin,manager,technician}'));

-- ---------- 3) Denetim kaydı (append-only, sistem yazar) ----------------
create table public.audit_logs (
  id           bigint generated always as identity primary key,
  tenant_id    uuid references public.tenants(id) on delete cascade,
  user_id      uuid references public.app_users(id) on delete set null,
  method       text not null,
  path         text not null,
  status       smallint not null,
  entity_type  text,          -- yolun ilk parçası: parts, assets, stock, organization...
  entity_id    uuid,          -- yoldaki ilk uuid
  action       text,          -- install, remove, create, update, login...
  detail       jsonb,         -- uç noktanın eklediği özet (ör. değişen eşikler)
  ip           text,
  user_agent   text,
  at           timestamptz not null default now()
);
create index on public.audit_logs (tenant_id, at desc);
create index on public.audit_logs (tenant_id, entity_id) where entity_id is not null;

alter table public.audit_logs enable row level security;
grant select on public.audit_logs to sparetwin_app;   -- insert yok: yalnızca sahip rolü yazar
create policy audit_logs_select on public.audit_logs for select to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin}'));
