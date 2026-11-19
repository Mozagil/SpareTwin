-- =====================================================================
-- SpareTwin — 0022: Üretim emrinin stokla bağı, fire ve hurda
-- ---------------------------------------------------------------------
-- Emir açılırken ürün ağacının (0020) birinci seviye bileşenleri emre
-- kopyalanır: planlanan miktar = ağaçtaki miktar × emir miktarı.
-- Emir tamamlanırken:
--   - her malzemenin gerçekleşen kullanımı girilir; stoktan o kadar düşülür,
--   - sağlam ve hurda ürün miktarı girilir; sağlam ürün stoğa girer.
--
--   production_order_materials → emrin malzemeleri: plan, gerçekleşen, sebep
--   production_orders          → + good_qty, scrap_qty, scrap_reason, site_id
--
-- Fire  = gerçekleşen − planlanan malzeme (eksi: tasarruf).
-- Hurda = üretilip kullanılamayan ürün.
-- Kurallar (prod_complete):
--   - Plandan fazla malzeme ve hurda ürün için sebep zorunludur.
--   - Stok yetmiyorsa emir tamamlanmaz (eksi stok yok).
--   - Seri numarasıyla tek tek izlenen kalemlerde (silindir, pompa…) stok
--     hareketi yapılmaz; plan / gerçekleşen yine kaydedilir.
--   - Alt montaj bileşenlerine açılmaz: stokta hazır olmalıdır (kendi emriyle üretilir).
-- =====================================================================

create domain app.scrap_reason as text
  check (value in ('material', 'workmanship', 'machine', 'setup', 'dimension', 'damage', 'other'));

alter table public.production_orders
  add column good_qty      numeric(14,4) check (good_qty >= 0),
  add column scrap_qty     numeric(14,4) check (scrap_qty >= 0),
  add column scrap_reason  app.scrap_reason,
  add column site_id       uuid references public.sites(id) on delete set null;   -- malzemenin çıktığı, ürünün girdiği depo

create table public.production_order_materials (
  id           bigint generated always as identity primary key,
  tenant_id    uuid not null references public.tenants(id) on delete cascade,
  order_id     uuid not null references public.production_orders(id) on delete cascade,
  part_id      uuid not null references public.parts(id),
  planned_qty  numeric(14,4) not null check (planned_qty > 0),   -- emrin tamamı için
  actual_qty   numeric(14,4) check (actual_qty >= 0),            -- emir tamamlanınca dolar
  reason       app.scrap_reason,                                 -- plandan fazla kullanımın sebebi
  unit_cost    numeric(12,4),                                    -- tüketim anındaki birim maliyet
  stock_moved  boolean not null default false,                   -- stoktan düşüldü mü (seri numaralı kalemde hayır)
  unique (order_id, part_id)
);
create index on public.production_order_materials (tenant_id, part_id);

alter table public.production_order_materials enable row level security;
grant select, insert, update on public.production_order_materials to sparetwin_app;
create policy prod_materials_select on public.production_order_materials for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy prod_materials_insert on public.production_order_materials for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager}'));
create policy prod_materials_update on public.production_order_materials for update to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager,technician}'));

-- Açık emirler: malzemeler bugünkü ürün ağacından doldurulur
insert into public.production_order_materials (tenant_id, order_id, part_id, planned_qty)
select o.tenant_id, o.id, l.part_id, l.qty * o.qty
  from public.production_orders o
  join public.boms b on b.part_id = o.part_id and b.tenant_id = o.tenant_id
  join public.bom_lines l on l.bom_id = b.id
 where o.status in ('open', 'in_progress');

-- ---------- Emri tamamla: malzeme çıkışı, ürün girişi, fire ve hurda ----------
-- p_materials: [{"part_id": …, "actual_qty": …, "reason": …}]; listede olmayan malzeme planlandığı kadar kullanılmış sayılır.
create or replace function public.prod_complete(
  p_order uuid, p_site uuid, p_good numeric, p_scrap numeric default 0,
  p_scrap_reason text default null, p_materials jsonb default '[]'
) returns public.production_orders
language plpgsql security invoker
set search_path = public, app
as $$
declare
  o     public.production_orders;
  m     record;
  x     jsonb;
  a     numeric;
  r     text;
  have  numeric;
  cost  numeric;
  mv    public.stock_movements;
  ser   boolean;
begin
  select * into o from public.production_orders where id = p_order for update;
  if not found then raise exception 'Üretim emri bulunamadı' using errcode = 'P0002'; end if;
  if o.status not in ('open', 'in_progress') then
    raise exception 'Emir zaten kapanmış' using errcode = '22023';
  end if;
  if exists (select 1 from public.production_order_ops where order_id = p_order and done_at is null) then
    raise exception 'Bitmemiş işlem var; emir bütün işlemler bitince tamamlanır' using errcode = '22023';
  end if;
  p_scrap := coalesce(p_scrap, 0);
  if p_good is null or p_good < 0 or p_scrap < 0 or p_good + p_scrap <= 0 then
    raise exception 'Sağlam ve hurda miktarı eksi olamaz; toplamı sıfırdan büyük olmalı' using errcode = '22023';
  end if;
  if p_scrap > 0 and p_scrap_reason is null then
    raise exception 'Hurda için sebep seçin' using errcode = '22023';
  end if;
  if p_site is not null and not exists (select 1 from public.sites where id = p_site and tenant_id = o.tenant_id) then
    raise exception 'Depo bulunamadı' using errcode = 'P0002';
  end if;

  for m in
    select pm.id, pm.part_id, pm.planned_qty, p.name, p.list_cost, pc.is_serialized
      from public.production_order_materials pm
      join public.parts p on p.id = pm.part_id
      join public.part_categories pc on pc.id = p.category_id
     where pm.order_id = p_order order by pm.id
  loop
    select e into x from jsonb_array_elements(coalesce(p_materials, '[]')) e where (e->>'part_id')::uuid = m.part_id limit 1;
    a := coalesce((x->>'actual_qty')::numeric, m.planned_qty);
    r := case when a > m.planned_qty then x->>'reason' end;
    if a < 0 then
      raise exception 'Kullanılan miktar eksi olamaz (%)', m.name using errcode = '22023';
    end if;
    if a > m.planned_qty and r is null then
      raise exception 'Plandan fazla kullanılan "%" için sebep seçin', m.name using errcode = '22023';
    end if;
    cost := null;
    if a > 0 and not m.is_serialized then
      have := app.stock_level(o.tenant_id, m.part_id, p_site);
      if a > have then
        raise exception '"%" için stok yetmiyor (depoda %, gereken %)', m.name, trim_scale(have), trim_scale(a) using errcode = '22023';
      end if;
      mv := public.stock_move(m.part_id, p_site, 'out', a, null, null, 'üretim', o.number, null, null, o.tenant_id);
      cost := mv.unit_cost;
    end if;
    update public.production_order_materials
       set actual_qty = a, reason = r, unit_cost = coalesce(cost, m.list_cost), stock_moved = (a > 0 and not m.is_serialized)
     where id = m.id;
  end loop;

  select pc.is_serialized into ser
    from public.parts p join public.part_categories pc on pc.id = p.category_id where p.id = o.part_id;
  if p_good > 0 and not ser then
    perform public.stock_move(o.part_id, p_site, 'in', p_good, null, null, 'üretim', o.number, null, null, o.tenant_id);
  end if;

  update public.production_orders
     set status = 'done', completed_at = now(), completed_by = app.current_user_id(),
         started_at = coalesce(started_at, now()),
         good_qty = p_good, scrap_qty = p_scrap, scrap_reason = case when p_scrap > 0 then p_scrap_reason end,
         site_id = p_site
   where id = p_order returning * into o;
  return o;
end $$;
grant execute on function public.prod_complete(uuid, uuid, numeric, numeric, text, jsonb) to sparetwin_app;

-- ---------- Durum: artık yalnızca iptal (tamamlama prod_complete ile) ----------
create or replace function public.prod_set_status(p_order uuid, p_status text)
returns public.production_orders
language plpgsql security invoker
set search_path = public, app
as $$
declare
  o public.production_orders;
begin
  select * into o from public.production_orders where id = p_order for update;
  if not found then raise exception 'Üretim emri bulunamadı' using errcode = 'P0002'; end if;
  if o.status not in ('open', 'in_progress') then
    raise exception 'Emir zaten kapanmış' using errcode = '22023';
  end if;
  if p_status <> 'cancelled' then
    raise exception 'Geçersiz durum: %', p_status using errcode = '22023';
  end if;
  update public.production_time_logs t set ended_at = now()
    from public.production_order_ops x
   where x.id = t.op_id and x.order_id = p_order and t.ended_at is null;
  update public.production_orders
     set status = 'cancelled', completed_at = now(), completed_by = app.current_user_id(),
         started_at = coalesce(started_at, now())
   where id = p_order returning * into o;
  return o;
end $$;
