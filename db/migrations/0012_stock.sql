-- =====================================================================
-- SpareTwin — 0012: Depo ve stok (Faz 2)
-- ---------------------------------------------------------------------
-- Seri numaralı parçalar (lastik, jant, silindir) zaten tek tek izleniyor:
-- stoktakiler part_items.status = 'in_stock'. Bu migrasyon, adetle / litreyle
-- izlenen sarf malzemeleri (filtre, yağ, keçe takımı) için bir hareket
-- defteri ekler. Stok seviyesi her zaman hareketlerden hesaplanır; ayrı bir
-- sayaç tutulmaz, böylece defterle sayı asla çelişmez. Defter append-only.
-- Depo = saha (sites). Saha boşsa "genel depo".
-- =====================================================================

alter table public.parts add column unit text not null default 'adet'
  check (unit in ('adet', 'litre', 'kg', 'metre', 'takım'));

insert into public.part_categories (tenant_id, code, name, is_serialized, measurement_profile, required_photo_angles) values
  (null, 'lubricant', 'Yağ ve gres', false, '[]', '{}'),
  (null, 'seal_kit', 'Keçe / conta takımı', false, '[]', '{}')
on conflict do nothing;

create type app.stock_move_kind as enum ('in', 'out', 'adjust', 'transfer_out', 'transfer_in');

create table public.stock_movements (
  id              bigint generated always as identity primary key,
  tenant_id       uuid not null references public.tenants(id) on delete cascade,
  part_id         uuid not null references public.parts(id),
  site_id         uuid references public.sites(id) on delete restrict,
  kind            app.stock_move_kind not null,
  qty             numeric(12,3) not null check (qty <> 0),   -- işaretli: giriş +, çıkış −
  unit_cost       numeric(12,4),                              -- girişte alış, çıkışta ortalama maliyet
  asset_id        uuid references public.assets(id) on delete set null,  -- çıkış hangi makineye
  transfer_group  uuid,
  reason          text,
  ref             text,                                       -- fatura / irsaliye / iş emri no
  notes           text,
  performed_by    uuid references public.app_users(id),
  occurred_at     timestamptz not null default now()
);
create index on public.stock_movements (tenant_id, part_id, site_id);
create index on public.stock_movements (asset_id) where asset_id is not null;

alter table public.stock_movements enable row level security;
grant select, insert on public.stock_movements to sparetwin_app;
grant usage on all sequences in schema public to sparetwin_app;
create policy stock_movements_select on public.stock_movements for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy stock_movements_insert on public.stock_movements for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager,technician}'));

-- ---------- Stok seviyeleri: kalem × depo ----------
create or replace view public.v_stock_levels
with (security_invoker = true) as
select sm.tenant_id, sm.part_id, sm.site_id, sum(sm.qty) as qty
  from public.stock_movements sm
 group by sm.tenant_id, sm.part_id, sm.site_id
union all
select pi.tenant_id, pi.part_id, pi.site_id, count(*)::numeric as qty
  from public.part_items pi
 where pi.status = 'in_stock'
 group by pi.tenant_id, pi.part_id, pi.site_id;

-- ---------- Kalem bazında toplam, değer, kritik seviye ----------
-- Firmanın kendi kalemleri; ortak kütüphanedeki kalemler, firmada stoğu varsa görünür.
create or replace view public.v_stock_totals
with (security_invoker = true) as
with t as (select distinct tenant_id from public.memberships)
select
  t.tenant_id,
  p.id as part_id, p.name, p.manufacturer, p.part_no, p.unit, p.min_stock,
  pc.code as category_code, pc.name as category_name, pc.is_serialized,
  coalesce(lv.qty, 0) as qty,
  case when pc.is_serialized then
    (select sum(pi.purchase_cost) from public.part_items pi
      where pi.part_id = p.id and pi.tenant_id = t.tenant_id and pi.status = 'in_stock')
  else coalesce(lv.qty, 0) * coalesce(ac.avg_cost, p.list_cost, 0) end as value,
  case when pc.is_serialized then p.list_cost else coalesce(ac.avg_cost, p.list_cost) end as avg_cost,
  coalesce(lv.qty, 0) < p.min_stock as below_min,
  lv.sites
from t
join public.parts p on p.tenant_id = t.tenant_id or p.tenant_id is null
join public.part_categories pc on pc.id = p.category_id
left join lateral (
  select sum(l.qty) as qty,
         jsonb_agg(jsonb_build_object('site_id', l.site_id, 'qty', l.qty) order by l.site_id) filter (where l.qty <> 0) as sites
    from (select site_id, sum(qty) as qty from public.v_stock_levels
           where tenant_id = t.tenant_id and part_id = p.id group by site_id) l
) lv on true
left join lateral (
  -- Ağırlıklı ortalama alış maliyeti (fiyatlı girişlerden)
  select sum(sm.qty * sm.unit_cost) / nullif(sum(sm.qty), 0) as avg_cost
    from public.stock_movements sm
   where sm.tenant_id = t.tenant_id and sm.part_id = p.id and sm.kind = 'in' and sm.unit_cost is not null
) ac on true
where p.tenant_id = t.tenant_id or coalesce(lv.qty, 0) <> 0 or exists (
  select 1 from public.part_items x where x.part_id = p.id and x.tenant_id = t.tenant_id);

grant select on public.v_stock_levels, public.v_stock_totals to sparetwin_app;

-- ---------- Hareket fonksiyonları (kurallar tek yerde) ----------
create or replace function app.stock_level(p_tenant uuid, p_part uuid, p_site uuid)
returns numeric language sql stable as $$
  select coalesce(sum(qty), 0) from public.stock_movements
   where tenant_id = p_tenant and part_id = p_part and site_id is not distinct from p_site;
$$;
grant execute on function app.stock_level(uuid, uuid, uuid) to sparetwin_app;

-- p_kind: 'in' (giriş), 'out' (çıkış/kullanım), 'adjust' (sayım: p_qty = sayılan miktar),
--         'transfer_out' / 'transfer_in' (yalnızca stock_transfer kullanır)
create or replace function public.stock_move(
  p_part uuid, p_site uuid, p_kind text, p_qty numeric,
  p_unit_cost numeric default null, p_asset uuid default null,
  p_reason text default null, p_ref text default null, p_notes text default null,
  p_group uuid default null, p_tenant uuid default null
) returns public.stock_movements
language plpgsql security invoker
set search_path = public, app
as $$
declare
  part   record;
  t      uuid;
  cur    numeric;
  delta  numeric;
  cost   numeric;
  mv     public.stock_movements;
begin
  select p.id, p.tenant_id, p.list_cost, pc.is_serialized into part
    from public.parts p join public.part_categories pc on pc.id = p.category_id where p.id = p_part;
  if not found then raise exception 'Katalog kalemi bulunamadı' using errcode = 'P0002'; end if;
  if part.is_serialized then
    raise exception 'Bu kalem seri numarasıyla tek tek izlenir; stoğa "Parça teslim al" ile girin' using errcode = '22023';
  end if;
  -- Firma: kendi kalemi ise o firma; ortak kütüphane kalemi ise çağıranın belirttiği firma.
  -- (Ekleme izni RLS'te ayrıca kontrol edilir: kullanıcı o firmada teknisyen veya üstü olmalı.)
  t := coalesce(part.tenant_id, p_tenant);
  if t is null then
    raise exception 'Firma belirtilmeli' using errcode = '22023';
  end if;
  if p_site is not null and not exists (select 1 from public.sites where id = p_site and tenant_id = t) then
    raise exception 'Depo bulunamadı' using errcode = 'P0002';
  end if;
  if p_asset is not null and not exists (select 1 from public.assets where id = p_asset and tenant_id = t) then
    raise exception 'Makine bulunamadı' using errcode = 'P0002';
  end if;
  if p_qty is null or (p_kind <> 'adjust' and p_qty <= 0) or p_qty < 0 then
    raise exception 'Miktar sıfırdan büyük olmalı' using errcode = '22023';
  end if;

  -- Aynı kalem + depo için eşzamanlı hareketler sıraya girer (eksi stok yarışı olmasın)
  perform pg_advisory_xact_lock(hashtextextended(p_part::text || coalesce(p_site::text, ''), 0));
  cur := app.stock_level(t, p_part, p_site);
  select sum(sm.qty * sm.unit_cost) / nullif(sum(sm.qty), 0) into cost
    from public.stock_movements sm
   where sm.tenant_id = t and sm.part_id = p_part and sm.kind = 'in' and sm.unit_cost is not null;
  cost := coalesce(cost, part.list_cost);

  if p_kind in ('in', 'transfer_in') then
    delta := p_qty; cost := coalesce(p_unit_cost, cost);
  elsif p_kind in ('out', 'transfer_out') then
    if p_qty > cur then
      raise exception 'Stokta yeterli yok (depoda %, istenen %)', trim_scale(cur), trim_scale(p_qty) using errcode = '22023';
    end if;
    delta := -p_qty;
  elsif p_kind = 'adjust' then
    delta := p_qty - cur;  -- sayılan miktar ile kayıtlı arasındaki fark
    if delta = 0 then
      raise exception 'Sayılan miktar kayıtlı miktarla aynı; düzeltme gerekmiyor' using errcode = '22023';
    end if;
  else
    raise exception 'Geçersiz hareket türü: %', p_kind using errcode = '22023';
  end if;

  insert into public.stock_movements
    (tenant_id, part_id, site_id, kind, qty, unit_cost, asset_id, transfer_group, reason, ref, notes, performed_by)
  values (t, p_part, p_site, p_kind::app.stock_move_kind, delta, cost, case when p_kind = 'out' then p_asset end,
          p_group, p_reason, p_ref, p_notes, app.current_user_id())
  returning * into mv;
  return mv;
end $$;

-- Transfer: aynı işlemde kaynaktan çıkış + hedefe giriş. Yetki yükseltmesi yok; her iki
-- hareket de stock_move'un kontrollerinden (firma, depo, eksi stok) geçer.
create or replace function public.stock_transfer(p_part uuid, p_from uuid, p_to uuid, p_qty numeric,
                                                 p_notes text default null, p_tenant uuid default null)
returns uuid
language plpgsql security invoker
set search_path = public, app
as $$
declare
  g uuid := gen_random_uuid();
  o public.stock_movements;
begin
  if p_from is not distinct from p_to then
    raise exception 'Kaynak ve hedef depo aynı olamaz' using errcode = '22023';
  end if;
  o := public.stock_move(p_part, p_from, 'transfer_out', p_qty, null, null, 'transfer', null, p_notes, g, p_tenant);
  perform public.stock_move(p_part, p_to, 'transfer_in', p_qty, o.unit_cost, null, 'transfer', null, p_notes, g, p_tenant);
  return g;
end $$;

grant execute on function public.stock_move(uuid, uuid, text, numeric, numeric, uuid, text, text, text, uuid, uuid) to sparetwin_app;
grant execute on function public.stock_transfer(uuid, uuid, uuid, numeric, text, uuid) to sparetwin_app;
