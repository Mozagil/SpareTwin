-- =====================================================================
-- SpareTwin — 0001: Çekirdek dijital parça ikizi şeması
-- ---------------------------------------------------------------------
-- Temel fikir: Her fiziksel parça (lastik, jant, hidrolik silindir,
-- pompa, zincir...) bir "parça ikizi" (part_item) olarak yaşar.
-- Lastiğe özgü hiçbir kolon bu dosyada yoktur; lastik/jant bilgisi
-- 0004 modül migrasyonunda uzantı tablolarıyla eklenir.
--
-- Roller:
--   * Migrasyonları çalıştıran kullanıcı (sahip) tabloların sahibidir.
--   * sparetwin_app: API'nin her istekte geçtiği kısıtlı rol (SET LOCAL ROLE).
--     RLS bu role uygulanır; firma izolasyonu buna dayanır.
-- =====================================================================

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'sparetwin_app') then
    create role sparetwin_app nologin noinherit;
  end if;
end $$;
-- Sahip kullanıcı, istek başında bu role geçebilsin
grant sparetwin_app to current_user;

create schema if not exists app;

-- İstek sahibinin kimliği. API her işlem başında set_config('app.user_id', ...) yapar.
create or replace function app.current_user_id()
returns uuid language sql stable as $$
  select nullif(current_setting('app.user_id', true), '')::uuid;
$$;

-- ---------- Enum tipleri ---------------------------------------------
create type app.member_role as enum ('owner', 'admin', 'manager', 'technician', 'viewer');

create type app.asset_status as enum ('active', 'down', 'maintenance', 'retired');

create type app.part_item_status as enum (
  'in_stock',     -- depoda, takılmaya hazır
  'installed',    -- bir makinenin bir pozisyonunda
  'in_repair',    -- tamirde
  'refurbishing', -- yenilemede (lastik için kaplama/retread)
  'quarantine',   -- kontrol bekliyor
  'scrapped'      -- hurdaya ayrıldı
);

create type app.part_event_type as enum (
  'received', 'installed', 'removed', 'inspected', 'repaired',
  'refurbished', 'rotated', 'transferred', 'scrapped', 'note'
);

create type app.measure_source as enum ('manual', 'sensor', 'telematics', 'import');

create type app.inspection_status as enum ('draft', 'completed', 'rejected');

-- ---------- Ortak yardımcılar ----------------------------------------
create or replace function app.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- ---------- Firma (tenant) ve kullanıcılar ---------------------------
create table public.tenants (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  slug        text not null unique check (slug ~ '^[a-z0-9-]{3,40}$'),
  plan        text not null default 'pilot',
  settings    jsonb not null default '{}'::jsonb,  -- örn. {"currency":"TRY","hour_cost_basis":"engine_hours"}
  created_at  timestamptz not null default now()
);

create table public.app_users (
  id                 uuid primary key default gen_random_uuid(),
  email              text not null,
  password_hash      text not null,             -- argon2id; API rolü bu kolonu okuyamaz
  full_name          text,
  locale             text not null default 'tr',
  is_active          boolean not null default true,
  is_platform_admin  boolean not null default false,
  last_login_at      timestamptz,
  created_at         timestamptz not null default now()
);
create unique index app_users_email_uq on public.app_users (lower(email));

-- Yenileme (refresh) token'ları: yalnızca SHA-256 özeti saklanır, her kullanımda döner.
create table public.refresh_tokens (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.app_users(id) on delete cascade,
  token_hash   text not null unique,
  expires_at   timestamptz not null,
  revoked_at   timestamptz,
  replaced_by  uuid,
  user_agent   text,
  created_at   timestamptz not null default now()
);
create index on public.refresh_tokens (user_id);

create table public.memberships (
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  user_id     uuid not null references public.app_users(id) on delete cascade,
  role        app.member_role not null default 'viewer',
  created_at  timestamptz not null default now(),
  primary key (tenant_id, user_id)
);

create table public.sites (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  name        text not null,
  kind        text,            -- 'maden', 'liman', 'şantiye', 'fabrika', 'depo'
  city        text,
  created_at  timestamptz not null default now(),
  unique (tenant_id, name)
);

-- ---------- Pozisyon şablonları --------------------------------------
-- Bir makine modelinde parçaların takılabileceği "yuvalar".
-- tenant_id null ise platformun ortak kütüphanesidir.
create table public.position_templates (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid references public.tenants(id) on delete cascade,
  name        text not null,
  layout      text not null default 'generic', -- dashboard çizimi için: 'loader', 'reach_stacker', 'forklift', 'generic'
  created_at  timestamptz not null default now()
);

create table public.template_positions (
  template_id   uuid not null references public.position_templates(id) on delete cascade,
  code          text not null,           -- 'A1-L', 'A2-RO', 'LIFT-CYL-L'
  label         text not null,           -- 'Ön aks sol'
  category_code text not null,           -- hangi parça kategorisi takılır: 'tire', 'rim', 'hyd_cylinder'
  axle          smallint,                -- lastikler için aks no (1 = ön)
  x             numeric(5,2),            -- şema üzerinde 0–100 yatay konum
  y             numeric(5,2),            -- şema üzerinde 0–100 dikey konum
  sort_order    smallint not null default 0,
  primary key (template_id, code)
);

-- ---------- Makine / ekipman (varlık) --------------------------------
create table public.asset_models (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid references public.tenants(id) on delete cascade,
  manufacturer  text not null,
  model         text not null,
  category      text not null,           -- 'wheel_loader', 'haul_truck', 'reach_stacker', 'forklift', 'press', 'cnc'...
  template_id   uuid references public.position_templates(id),
  created_at    timestamptz not null default now()
);

create table public.assets (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  site_id       uuid references public.sites(id) on delete set null,
  model_id      uuid references public.asset_models(id),
  code          text not null,           -- filo/ekipman no: 'LD-07'
  serial_no     text,
  year          smallint,
  status        app.asset_status not null default 'active',
  meter_hours   numeric(10,1) not null default 0,  -- güncel motor saati
  meter_km      numeric(10,1) not null default 0,
  qr_code       text unique,
  notes         text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (tenant_id, code)
);
create trigger trg_assets_updated before update on public.assets
  for each row execute function app.touch_updated_at();

create table public.meter_readings (
  id          bigint generated always as identity primary key,
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  asset_id    uuid not null references public.assets(id) on delete cascade,
  hours       numeric(10,1),
  km          numeric(10,1),
  source      app.measure_source not null default 'manual',
  read_at     timestamptz not null default now(),
  read_by     uuid references public.app_users(id)
);
create index on public.meter_readings (asset_id, read_at desc);

-- ---------- Parça kataloğu ve parça ikizi ----------------------------
create table public.part_categories (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid references public.tenants(id) on delete cascade,
  code                text not null,     -- 'tire', 'rim', 'hyd_cylinder', 'hyd_pump', 'chain', 'filter'
  name                text not null,
  is_serialized       boolean not null default true,   -- seri numarasıyla tek tek izlenir mi?
  measurement_profile jsonb not null default '[]'::jsonb,
  -- örn. [{"metric":"tread_depth_mm","label":"Diş derinliği","unit":"mm","required":true,"min":0,"max":200}]
  required_photo_angles text[] not null default '{}',  -- inspeksiyonda zorunlu fotoğraf açıları
  created_at          timestamptz not null default now()
);
create unique index part_categories_code_uq
  on public.part_categories (coalesce(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), code);

create table public.parts (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid references public.tenants(id) on delete cascade, -- null = ortak katalog
  category_id   uuid not null references public.part_categories(id),
  manufacturer  text,
  part_no       text,
  name          text not null,
  specs         jsonb not null default '{}'::jsonb,
  list_cost     numeric(12,2),
  min_stock     integer not null default 0,     -- kritik stok seviyesi (seri olmayan parçalar için de)
  created_at    timestamptz not null default now()
);

create table public.part_items (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references public.tenants(id) on delete cascade,
  part_id             uuid not null references public.parts(id),
  serial_no           text,
  qr_code             text unique,
  status              app.part_item_status not null default 'in_stock',
  site_id             uuid references public.sites(id) on delete set null,
  current_asset_id    uuid references public.assets(id) on delete set null,
  current_position    text,
  installed_at_hours  numeric(10,1),          -- takıldığında makinenin saati
  installed_at_km     numeric(10,1),
  hours_accumulated   numeric(10,1) not null default 0,  -- önceki montajlarda biriken saat
  km_accumulated      numeric(10,1) not null default 0,
  purchase_cost       numeric(12,2),
  acquired_at         date,
  attributes          jsonb not null default '{}'::jsonb,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint installed_needs_position check (
    (status = 'installed') = (current_asset_id is not null and current_position is not null)
  )
);
create trigger trg_part_items_updated before update on public.part_items
  for each row execute function app.touch_updated_at();
-- Aynı makinenin aynı pozisyonuna iki parça takılamaz.
create unique index part_items_one_per_position
  on public.part_items (current_asset_id, current_position)
  where status = 'installed';
create index on public.part_items (tenant_id, status);

-- Yaşam döngüsü defteri: append-only. Parçanın tüm geçmişi buradan okunur.
create table public.part_events (
  id            bigint generated always as identity primary key,
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  part_item_id  uuid not null references public.part_items(id) on delete cascade,
  event_type    app.part_event_type not null,
  asset_id      uuid references public.assets(id) on delete set null,
  position      text,
  asset_hours   numeric(10,1),
  asset_km      numeric(10,1),
  part_hours    numeric(10,1),   -- olay anında parçanın toplam çalışma saati
  cost          numeric(12,2),
  reason_code   text,            -- sökme/hurda sebebi: 'worn_out', 'cut', 'impact', 'leak', 'rotation'...
  notes         text,
  performed_by  uuid references public.app_users(id),
  occurred_at   timestamptz not null default now()
);
create index on public.part_events (part_item_id, occurred_at desc);

-- ---------- İnspeksiyon ve ölçümler ----------------------------------
create table public.inspections (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  asset_id      uuid not null references public.assets(id) on delete cascade,
  status        app.inspection_status not null default 'draft',
  asset_hours   numeric(10,1),
  asset_km      numeric(10,1),
  qc_flags      jsonb not null default '[]'::jsonb,  -- kalite kapısı sonuçları
  inspected_by  uuid references public.app_users(id),
  started_at    timestamptz not null default now(),
  completed_at  timestamptz
);
create index on public.inspections (asset_id, started_at desc);

create table public.measurements (
  id             bigint generated always as identity primary key,
  tenant_id      uuid not null references public.tenants(id) on delete cascade,
  part_item_id   uuid not null references public.part_items(id) on delete cascade,
  inspection_id  uuid references public.inspections(id) on delete cascade,
  metric         text not null,     -- 'tread_depth_mm', 'pressure_kpa', 'temperature_c', 'stroke_leak_mm'...
  value          numeric(12,3) not null,
  unit           text,
  source         app.measure_source not null default 'manual',
  asset_hours    numeric(10,1),
  measured_at    timestamptz not null default now()
);
create index on public.measurements (part_item_id, metric, measured_at desc);
-- Bir inspeksiyonda her parça+ölçüm bir kez; tekrar girilen değer güncellenir
create unique index measurements_inspection_uq
  on public.measurements (inspection_id, part_item_id, metric) where inspection_id is not null;

-- Fotoğraf/doküman kayıtları. Dosyanın kendisi depoda (yerel disk veya S3 uyumlu) durur;
-- erişim her zaman API üzerinden, bu tablodaki yetkiye göre verilir.
create table public.attachments (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  entity_type   text not null check (entity_type in ('asset','part_item','inspection','part_event','part')),
  entity_id     uuid not null,
  part_item_id  uuid references public.part_items(id) on delete cascade, -- inspeksiyon fotoğrafı hangi parçaya ait
  storage_key   text not null unique, -- depo içindeki anahtar: '{tenant_id}/inspection/{entity_id}/{uuid}.jpg'
  file_name     text,
  mime_type     text not null,
  size_bytes    bigint not null check (size_bytes > 0),
  kind          text not null default 'photo',  -- 'photo', 'certificate', 'drawing', 'report'
  angle         text,              -- fotoğraf açısı: 'sidewall', 'tread', 'damage_closeup'
  created_by    uuid references public.app_users(id),
  created_at    timestamptz not null default now()
);
create index on public.attachments (entity_type, entity_id);
-- İnspeksiyonda her parça+açı için tek fotoğraf; yenisi eskisinin yerine geçer
create unique index attachments_inspection_angle_uq
  on public.attachments (entity_id, part_item_id, angle) where entity_type = 'inspection';
