-- =====================================================================
-- SpareTwin — 0019: Model parça listesi (kritik parça listesi, BOM)
-- ---------------------------------------------------------------------
-- Bir makine modelinde hangi yuvaya hangi katalog kalemi uyar ve makine
-- genelinde hangi sarf / yedek kalemler kullanılır. Üreticinin binlerce
-- satırlık tam kataloğu değil, firmanın izlediği kritik kalemler hedeftir.
--
--   position_code dolu → "bu yuvaya bu kalem uyar" (bir yuvaya birden çok
--                         alternatif yazılabilir; miktar her zaman 1)
--   position_code boş  → makine geneli: sarf (filtre, yağ) ya da yedek;
--                         miktar makine başına kullanımı söyler
--
-- Liste firmaya aittir (ortak kütüphanedeki modele de her firma kendi
-- listesini yazar). Takma kuralı değişmez: yuvanın parça tipi yine
-- install_part_item'da denetlenir; liste yol gösterir, engel koymaz.
-- =====================================================================

create table public.model_parts (
  id             bigint generated always as identity primary key,
  tenant_id      uuid not null references public.tenants(id) on delete cascade,
  model_id       uuid not null references public.asset_models(id) on delete cascade,
  part_id        uuid not null references public.parts(id) on delete cascade,
  position_code  text,
  qty            numeric(12,3) not null default 1 check (qty > 0),
  notes          text,
  created_by     uuid references public.app_users(id) on delete set null,
  created_at     timestamptz not null default now()
);
-- Aynı kalem aynı yuvaya (ya da makine geneline) bir kez yazılır
create unique index model_parts_uq
  on public.model_parts (tenant_id, model_id, part_id, coalesce(position_code, ''));
create index on public.model_parts (model_id);

alter table public.model_parts enable row level security;
grant select, insert, update, delete on public.model_parts to sparetwin_app;
create policy model_parts_select on public.model_parts for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy model_parts_write on public.model_parts for all to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager}'))
  with check (app.has_role(tenant_id, '{owner,admin,manager}'));
