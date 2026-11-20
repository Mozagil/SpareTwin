-- =====================================================================
-- SpareTwin — 0025: Mühendislik ağacı (eBOM) ve eBOM → mBOM kuralları
-- ---------------------------------------------------------------------
-- eBOM tasarımın ağacıdır: üründe hangi parçalar var. Üretimin kullandığı
-- ağaç (mBOM) 0020'deki boms / bom_lines olarak kalır; emir, üretilebilirlik
-- ve maliyet ona bakar. Bu migrasyon eBOM'u ayrı tutar ve firmanın bir kez
-- tanımladığı kurallarla mBOM'a dönüştürülmesini sağlar.
--
--   eboms / ebom_lines → boms / bom_lines ile aynı biçim (ürün başına bir ağaç)
--   bom_rules          → firma kuralları
--
-- Kural tipleri (uygulama sırası sabittir, api/ebom.py):
--   flatten    → eşleşen alt montaj ayrı üretilmez, bileşenleri üst ürüne açılır
--   exclude    → eşleşen kalem mBOM'a girmez (referans, doküman)
--   substitute → eşleşen kalem yerine target_part_id kullanılır (qty = oran)
--   add        → target_part_id eklenir: ürün başına ya da eşleşen her birim
--                başına qty kadar (sarf, ambalaj)
--   scrap      → eşleşen kalemin miktarı %scrap_pct artar (fire payı)
--
-- Eşleşme: match_part_id (tek kalem), match_category (parça tipi kodu) ya da
-- ikisi de boş (bütün kalemler). Dönüşüm hesaplanır, saklanmaz: eBOM ya da
-- kural değişince önizleme değişir; mBOM yalnızca "üretim ağacına yaz"
-- denince güncellenir.
-- =====================================================================

create table public.eboms (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  part_id     uuid not null references public.parts(id) on delete cascade,  -- tasarlanan ürün
  notes       text,
  created_by  uuid references public.app_users(id) on delete set null,
  created_at  timestamptz not null default now(),
  unique (tenant_id, part_id)
);

create table public.ebom_lines (
  id          bigint generated always as identity primary key,
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  bom_id      uuid not null references public.eboms(id) on delete cascade,
  part_id     uuid not null references public.parts(id) on delete cascade,  -- bileşen
  qty         numeric(14,4) not null check (qty > 0),
  notes       text,
  created_at  timestamptz not null default now(),
  unique (bom_id, part_id)
);
create index on public.ebom_lines (tenant_id, part_id);

create table public.bom_rules (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references public.tenants(id) on delete cascade,
  action          text not null check (action in ('flatten', 'exclude', 'substitute', 'add', 'scrap')),
  match_part_id   uuid references public.parts(id) on delete cascade,
  match_category  text,
  target_part_id  uuid references public.parts(id) on delete cascade,   -- substitute: yerine geçen; add: eklenen
  qty             numeric(14,4) check (qty > 0),                         -- substitute: oran; add: miktar
  per             text check (per in ('product', 'match')),              -- add: ürün başına / eşleşen birim başına
  scrap_pct       numeric(6,2) check (scrap_pct > 0 and scrap_pct <= 100),
  is_active       boolean not null default true,
  created_by      uuid references public.app_users(id) on delete set null,
  created_at      timestamptz not null default now(),
  constraint bom_rules_one_match check (match_part_id is null or match_category is null),
  constraint bom_rules_shape check (
    case action
      when 'scrap'      then scrap_pct is not null
      when 'substitute' then match_part_id is not null and target_part_id is not null and qty is not null
                             and target_part_id <> match_part_id
      when 'add'        then target_part_id is not null and qty is not null and per is not null
      when 'exclude'    then match_part_id is not null or match_category is not null
      else                   match_part_id is not null or match_category is not null   -- flatten
    end)
);
create index on public.bom_rules (tenant_id, created_at);

do $$
declare
  t text;
begin
  foreach t in array array['eboms', 'ebom_lines', 'bom_rules'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('grant select, insert, update, delete on public.%I to sparetwin_app', t);
    execute format(
      'create policy %1$s_select on public.%1$I for select to sparetwin_app using (app.is_member(tenant_id))', t);
    execute format(
      'create policy %1$s_write on public.%1$I for all to sparetwin_app
         using (app.has_role(tenant_id, ''{owner,admin,manager}''))
         with check (app.has_role(tenant_id, ''{owner,admin,manager}''))', t);
  end loop;
end $$;
