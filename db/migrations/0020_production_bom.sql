-- =====================================================================
-- SpareTwin — 0020: Ürün ağacı (üretim BOM'u)
-- ---------------------------------------------------------------------
-- Firmanın ürettiği bir katalog kalemi hangi kalemlerden, kaçar birim
-- oluşur. Ürün de bileşen de aynı katalogdadır (parts). Bir bileşenin
-- kendi ürün ağacı varsa alt montajdır; ağaç böyle çok seviyeli olur.
--
--   boms       → üretilen kalem başına bir ürün ağacı
--   bom_lines  → bir üst seviye için bileşen ve miktar (1 birim ürün için)
--
-- Döngü (A'nın içinde B, B'nin içinde A) API'de satır eklenirken ve içe
-- aktarmada denetlenir. Model parça listesinden (0019, model_parts) ayrıdır:
-- o sahadaki makinenin bakımına, bu üretime bakar.
-- =====================================================================

create table public.boms (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  part_id     uuid not null references public.parts(id) on delete cascade,  -- üretilen kalem
  notes       text,
  created_by  uuid references public.app_users(id) on delete set null,
  created_at  timestamptz not null default now(),
  unique (tenant_id, part_id)
);

create table public.bom_lines (
  id          bigint generated always as identity primary key,
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  bom_id      uuid not null references public.boms(id) on delete cascade,
  part_id     uuid not null references public.parts(id) on delete cascade,  -- bileşen
  qty         numeric(14,4) not null check (qty > 0),
  notes       text,
  created_at  timestamptz not null default now(),
  unique (bom_id, part_id)
);
create index on public.bom_lines (tenant_id, part_id);

alter table public.boms enable row level security;
alter table public.bom_lines enable row level security;
grant select, insert, update, delete on public.boms, public.bom_lines to sparetwin_app;
create policy boms_select on public.boms for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy boms_write on public.boms for all to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager}'))
  with check (app.has_role(tenant_id, '{owner,admin,manager}'));
create policy bom_lines_select on public.bom_lines for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy bom_lines_write on public.bom_lines for all to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager}'))
  with check (app.has_role(tenant_id, '{owner,admin,manager}'));
