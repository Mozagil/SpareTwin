-- =====================================================================
-- SpareTwin — 0023: Üretim maliyeti (malzeme + işçilik + makine saati)
-- ---------------------------------------------------------------------
-- Maliyet emir tamamlanırken hesaplanır ve emre yazılır; sonradan değişen
-- oran ya da stok maliyeti kapanmış emri değiştirmez.
--
--   Malzeme   Σ kullanılan miktar × tüketim anındaki birim maliyet (0022).
--   İşçilik   Σ zaman kayıtları (saat) × firmanın işçilik saat maliyeti
--             (tenants.settings->'thresholds'->>'labor_cost_per_hour', varsayılan 0).
--   Makine    Σ işlemin zaman kayıtları (saat) × işlemin makine saat maliyeti.
--             Oran rotada işleme yazılır, emir açılırken emre kopyalanır;
--             boş = bu işlemde makine maliyeti yok.
--
--   bom_operations, production_order_ops → + machine_rate
--   production_orders → + labor_rate, material_cost, labor_cost, machine_cost
--
-- Birim maliyet = toplam / sağlam ürün: hurdanın maliyeti sağlam ürüne biner.
-- Sağlam ürün stoğa bu birim maliyetle girer (alt montaj üst ürüne maliyetiyle taşınır).
-- =====================================================================

alter table public.bom_operations
  add column machine_rate numeric(10,2) check (machine_rate >= 0 and machine_rate <= 100000);   -- makine saat maliyeti; boş = yok
alter table public.production_order_ops
  add column machine_rate numeric(10,2);

alter table public.production_orders
  add column labor_rate     numeric(10,2),     -- tamamlanma anındaki işçilik saat maliyeti
  add column material_cost  numeric(14,2),
  add column labor_cost     numeric(14,2),
  add column machine_cost   numeric(14,2);

comment on column public.production_orders.material_cost is
  'Emir tamamlanınca dolar; toplam = material_cost + labor_cost + machine_cost';

-- ---------- İşlem başına gerçekleşen süre (+ makine saat maliyeti) ----------
create or replace view public.v_production_ops
with (security_invoker = true) as
select x.id, x.tenant_id, x.order_id, x.seq, x.name, x.planned_minutes, x.done_at, x.done_by,
       coalesce(t.actual_minutes, 0) as actual_minutes,
       coalesce(t.running, 0) as running,
       x.machine_rate
  from public.production_order_ops x
  left join lateral (
    select round(sum(extract(epoch from (coalesce(l.ended_at, now()) - l.started_at)) / 60)::numeric, 1) as actual_minutes,
           count(*) filter (where l.ended_at is null) as running
      from public.production_time_logs l where l.op_id = x.id
  ) t on true;

-- ---------- Emri tamamla: 0022 + maliyet ----------
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
  rate  numeric;
  c_mat numeric;
  c_lab numeric;
  c_mac numeric;
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

  -- Maliyet: malzeme + işçilik + makine
  select coalesce((t.settings->'thresholds'->>'labor_cost_per_hour')::numeric, 0) into rate
    from public.tenants t where t.id = o.tenant_id;
  rate := coalesce(rate, 0);
  select round(coalesce(sum(pm.actual_qty * pm.unit_cost), 0), 2) into c_mat
    from public.production_order_materials pm where pm.order_id = p_order;
  select round(coalesce(sum(s.hours), 0) * rate, 2), round(coalesce(sum(s.hours * s.machine_rate), 0), 2)
    into c_lab, c_mac
    from (
      select op.machine_rate,
             (select coalesce(sum(extract(epoch from (l.ended_at - l.started_at))), 0) / 3600
                from public.production_time_logs l where l.op_id = op.id and l.ended_at is not null)::numeric as hours
        from public.production_order_ops op where op.order_id = p_order
    ) s;

  select pc.is_serialized into ser
    from public.parts p join public.part_categories pc on pc.id = p.category_id where p.id = o.part_id;
  if p_good > 0 and not ser then
    -- Sağlam ürün stoğa üretim birim maliyetiyle girer; maliyet hesaplanamadıysa stoktaki ortalama kalır
    perform public.stock_move(o.part_id, p_site, 'in', p_good,
                              case when c_mat + c_lab + c_mac > 0 then round((c_mat + c_lab + c_mac) / p_good, 4) end,
                              null, 'üretim', o.number, null, null, o.tenant_id);
  end if;

  update public.production_orders
     set status = 'done', completed_at = now(), completed_by = app.current_user_id(),
         started_at = coalesce(started_at, now()),
         good_qty = p_good, scrap_qty = p_scrap, scrap_reason = case when p_scrap > 0 then p_scrap_reason end,
         site_id = p_site,
         labor_rate = rate, material_cost = c_mat, labor_cost = c_lab, machine_cost = c_mac
   where id = p_order returning * into o;
  return o;
end $$;
