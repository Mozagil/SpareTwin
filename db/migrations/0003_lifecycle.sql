-- =====================================================================
-- SpareTwin — Yaşam döngüsü iş kuralları (API katmanı çağırır)
-- ---------------------------------------------------------------------
-- API tablolara doğrudan "status = installed" yazmaz; bu fonksiyonları
-- çağırır. Böylece saat hesabı, pozisyon kontrolü ve olay kaydı her
-- zaman aynı kuralla ve tek işlemde (transaction) yapılır.
-- Fonksiyonlar SECURITY INVOKER çalışır: çağıranın (sparetwin_app) RLS kuralları geçerli.
-- =====================================================================

-- ---------- Makine sayaç okuması -------------------------------------
create or replace function public.record_meter_reading(
  p_asset uuid,
  p_hours numeric default null,
  p_km    numeric default null,
  p_source app.measure_source default 'manual'
) returns public.assets
language plpgsql security invoker
set search_path = public, app
as $$
declare
  a public.assets;
begin
  select * into a from public.assets where id = p_asset for update;
  if not found then
    raise exception 'Makine bulunamadı' using errcode = 'P0002';
  end if;
  if p_hours is not null and p_hours < a.meter_hours then
    raise exception 'Motor saati geri gidemez (mevcut %, girilen %)', a.meter_hours, p_hours
      using errcode = '22023';
  end if;
  if p_km is not null and p_km < a.meter_km then
    raise exception 'Kilometre geri gidemez (mevcut %, girilen %)', a.meter_km, p_km
      using errcode = '22023';
  end if;

  insert into public.meter_readings (tenant_id, asset_id, hours, km, source, read_by)
  values (a.tenant_id, a.id, p_hours, p_km, p_source, app.current_user_id());

  update public.assets
     set meter_hours = coalesce(p_hours, meter_hours),
         meter_km    = coalesce(p_km, meter_km)
   where id = a.id
  returning * into a;
  return a;
end $$;

-- ---------- Parça takma ----------------------------------------------
create or replace function public.install_part_item(
  p_item     uuid,
  p_asset    uuid,
  p_position text,
  p_hours    numeric default null,
  p_notes    text default null
) returns public.part_items
language plpgsql security invoker
set search_path = public, app
as $$
declare
  it        public.part_items;
  a         public.assets;
  cat_code  text;
  slot_cat  text;
  v_hours   numeric;
begin
  select * into it from public.part_items where id = p_item for update;
  if not found then raise exception 'Parça bulunamadı' using errcode = 'P0002'; end if;

  select * into a from public.assets where id = p_asset;
  if not found then raise exception 'Makine bulunamadı' using errcode = 'P0002'; end if;

  if it.tenant_id <> a.tenant_id then
    raise exception 'Parça ve makine farklı firmalara ait' using errcode = '42501';
  end if;
  if it.status <> 'in_stock' then
    raise exception 'Yalnızca stoktaki parça takılabilir (durum: %)', it.status using errcode = '22023';
  end if;

  -- Pozisyon makine modelinin şablonunda var mı ve doğru kategori mi?
  select pc.code into cat_code
    from public.parts p join public.part_categories pc on pc.id = p.category_id
   where p.id = it.part_id;

  select tp.category_code into slot_cat
    from public.asset_models am
    join public.template_positions tp on tp.template_id = am.template_id
   where am.id = a.model_id and tp.code = p_position;

  if slot_cat is null then
    raise exception 'Pozisyon % bu makine modelinde tanımlı değil', p_position using errcode = '22023';
  end if;
  if slot_cat <> cat_code then
    raise exception 'Pozisyon % "%" bekliyor, parça "%" kategorisinde', p_position, slot_cat, cat_code
      using errcode = '22023';
  end if;

  if exists (select 1 from public.part_items x
              where x.current_asset_id = a.id and x.current_position = p_position and x.status = 'installed') then
    raise exception 'Pozisyon % dolu; önce mevcut parçayı sökün', p_position using errcode = '23505';
  end if;

  v_hours := coalesce(p_hours, a.meter_hours);

  update public.part_items
     set status = 'installed',
         current_asset_id   = a.id,
         current_position   = p_position,
         site_id            = a.site_id,
         installed_at_hours = v_hours,
         installed_at_km    = a.meter_km
   where id = it.id
  returning * into it;

  insert into public.part_events
    (tenant_id, part_item_id, event_type, asset_id, position, asset_hours, asset_km, part_hours, notes, performed_by)
  values
    (it.tenant_id, it.id, 'installed', a.id, p_position, v_hours, a.meter_km, it.hours_accumulated, p_notes, app.current_user_id());

  return it;
end $$;

-- ---------- Parça sökme ----------------------------------------------
-- p_next_status: sökülen parça nereye gidiyor? in_stock | in_repair |
-- refurbishing | quarantine | scrapped
create or replace function public.remove_part_item(
  p_item        uuid,
  p_reason      text,
  p_next_status app.part_item_status default 'in_stock',
  p_hours       numeric default null,
  p_cost        numeric default null,
  p_notes       text default null
) returns public.part_items
language plpgsql security invoker
set search_path = public, app
as $$
declare
  it       public.part_items;
  a        public.assets;
  v_hours  numeric;
  v_km     numeric;
  v_delta  numeric;
begin
  select * into it from public.part_items where id = p_item for update;
  if not found then raise exception 'Parça bulunamadı' using errcode = 'P0002'; end if;
  if it.status <> 'installed' then
    raise exception 'Parça takılı değil (durum: %)', it.status using errcode = '22023';
  end if;
  if p_next_status = 'installed' then
    raise exception 'Sökülen parça doğrudan "installed" olamaz; install_part_item kullanın'
      using errcode = '22023';
  end if;

  select * into a from public.assets where id = it.current_asset_id;
  v_hours := coalesce(p_hours, a.meter_hours);
  v_km    := a.meter_km;
  v_delta := v_hours - coalesce(it.installed_at_hours, v_hours);
  if v_delta < 0 then
    raise exception 'Sökme saati (%) takma saatinden (%) küçük olamaz', v_hours, it.installed_at_hours
      using errcode = '22023';
  end if;

  insert into public.part_events
    (tenant_id, part_item_id, event_type, asset_id, position, asset_hours, asset_km, part_hours,
     cost, reason_code, notes, performed_by)
  values
    (it.tenant_id, it.id, 'removed', a.id, it.current_position, v_hours, v_km, it.hours_accumulated + v_delta,
     p_cost, p_reason, p_notes, app.current_user_id());

  if p_next_status = 'scrapped' then
    insert into public.part_events (tenant_id, part_item_id, event_type, part_hours, reason_code, performed_by)
    values (it.tenant_id, it.id, 'scrapped', it.hours_accumulated + v_delta, p_reason, app.current_user_id());
  end if;

  update public.part_items
     set status             = p_next_status,
         hours_accumulated  = hours_accumulated + v_delta,
         km_accumulated     = km_accumulated + greatest(v_km - coalesce(installed_at_km, v_km), 0),
         current_asset_id   = null,
         current_position   = null,
         installed_at_hours = null,
         installed_at_km    = null
   where id = it.id
  returning * into it;

  return it;
end $$;

-- ---------- İnspeksiyonu tamamlama: 4 kalite kapısı ------------------
-- KK1 Kimlik  : ölçülen parçalar gerçekten bu makinede takılı mı?
-- KK2 Fotoğraf: kategorinin zorunlu açıları yüklenmiş mi?
-- KK3 Ölçüm   : zorunlu ölçümler var mı, değerler makul aralıkta mı?
-- KK4 Sayaç   : motor saati önceki inspeksiyonla tutarlı mı?
-- Hata varsa inspeksiyon 'draft' kalır ve qc_flags döner; saha ekibi düzeltir.
create or replace function public.complete_inspection(p_inspection uuid)
returns public.inspections
language plpgsql security invoker
set search_path = public, app
as $$
declare
  ins      public.inspections;
  flags    jsonb := '[]'::jsonb;
  r        record;
  prof     jsonb;
  m        jsonb;
  v        numeric;
  prev_h   numeric;
begin
  select * into ins from public.inspections where id = p_inspection for update;
  if not found then raise exception 'İnspeksiyon bulunamadı' using errcode = 'P0002'; end if;
  if ins.status = 'completed' then return ins; end if;

  -- KK1: ölçümü olup bu makinede takılı olmayan parça
  for r in
    select distinct ms.part_item_id
      from public.measurements ms
      join public.part_items pi on pi.id = ms.part_item_id
     where ms.inspection_id = ins.id
       and (pi.current_asset_id is distinct from ins.asset_id or pi.status <> 'installed')
  loop
    flags := flags || jsonb_build_object('gate', 'KK1', 'part_item_id', r.part_item_id,
      'message', 'Ölçülen parça bu makinede takılı görünmüyor');
  end loop;

  -- Makinede takılı ve kategorisinde ölçüm profili olan her parça için KK2 + KK3
  for r in
    select pi.id, pi.current_position, pc.measurement_profile, pc.required_photo_angles
      from public.part_items pi
      join public.parts p on p.id = pi.part_id
      join public.part_categories pc on pc.id = p.category_id
     where pi.current_asset_id = ins.asset_id and pi.status = 'installed'
       and (jsonb_array_length(pc.measurement_profile) > 0 or cardinality(pc.required_photo_angles) > 0)
  loop
    -- KK2: zorunlu fotoğraf açıları
    if cardinality(r.required_photo_angles) > 0 and exists (
      select unnest(r.required_photo_angles)
      except
      select at.angle from public.attachments at
       where at.entity_type = 'inspection' and at.entity_id = ins.id
         and at.part_item_id = r.id
    ) then
      flags := flags || jsonb_build_object('gate', 'KK2', 'part_item_id', r.id,
        'position', r.current_position, 'message', 'Zorunlu fotoğraf açıları eksik');
    end if;

    -- KK3: zorunlu ölçümler ve aralık kontrolü
    prof := r.measurement_profile;
    for m in select * from jsonb_array_elements(prof) loop
      select ms.value into v
        from public.measurements ms
       where ms.inspection_id = ins.id and ms.part_item_id = r.id and ms.metric = m->>'metric'
       order by ms.measured_at desc limit 1;

      if v is null and coalesce((m->>'required')::boolean, false) then
        flags := flags || jsonb_build_object('gate', 'KK3', 'part_item_id', r.id,
          'position', r.current_position, 'metric', m->>'metric',
          'message', format('%s girilmedi', m->>'label'));
      elsif v is not null and (
            (m ? 'min' and v < (m->>'min')::numeric) or
            (m ? 'max' and v > (m->>'max')::numeric)) then
        flags := flags || jsonb_build_object('gate', 'KK3', 'part_item_id', r.id,
          'position', r.current_position, 'metric', m->>'metric', 'value', v,
          'message', format('%s makul aralık dışında, yeniden ölçün', m->>'label'));
      end if;
    end loop;
  end loop;

  -- KK4: motor saati tutarlılığı
  select i.asset_hours into prev_h
    from public.inspections i
   where i.asset_id = ins.asset_id and i.status = 'completed' and i.id <> ins.id
   order by i.completed_at desc limit 1;
  if ins.asset_hours is null then
    flags := flags || jsonb_build_object('gate', 'KK4', 'message', 'Motor saati girilmedi');
  elsif prev_h is not null and ins.asset_hours < prev_h then
    flags := flags || jsonb_build_object('gate', 'KK4',
      'message', format('Motor saati (%s) önceki inspeksiyondan (%s) düşük', ins.asset_hours, prev_h));
  end if;

  if jsonb_array_length(flags) > 0 then
    update public.inspections set qc_flags = flags where id = ins.id returning * into ins;
    return ins;
  end if;

  -- Başarılı: sayaç güncelle, her ölçülen parçaya 'inspected' olayı yaz
  if ins.asset_hours > (select meter_hours from public.assets where id = ins.asset_id) then
    perform public.record_meter_reading(ins.asset_id, ins.asset_hours, null, 'manual');
  end if;

  insert into public.part_events
    (tenant_id, part_item_id, event_type, asset_id, position, asset_hours, part_hours, performed_by)
  select ins.tenant_id, pi.id, 'inspected'::app.part_event_type, ins.asset_id, pi.current_position,
         ins.asset_hours,
         pi.hours_accumulated + greatest(ins.asset_hours - coalesce(pi.installed_at_hours, ins.asset_hours), 0),
         app.current_user_id()
    from public.part_items pi
   where pi.id in (select ms.part_item_id from public.measurements ms where ms.inspection_id = ins.id);

  update public.inspections
     set status = 'completed', qc_flags = '[]'::jsonb, completed_at = now()
   where id = ins.id
  returning * into ins;
  return ins;
end $$;

-- ---------- Serbest olay kaydı (tamir, NDT muayenesi, kaplama dönüşü...) --
-- Parçanın o anki toplam saati otomatik hesaplanıp olaya yazılır.
create or replace function public.log_part_event(
  p_item        uuid,
  p_event       app.part_event_type,
  p_reason      text default null,
  p_cost        numeric default null,
  p_notes       text default null,
  p_next_status app.part_item_status default null
) returns public.part_events
language plpgsql security invoker
set search_path = public, app
as $$
declare
  it  public.part_items;
  a   public.assets;
  ev  public.part_events;
  v_part_hours numeric;
begin
  if p_event in ('installed', 'removed') then
    raise exception 'Takma/sökme için install_part_item / remove_part_item kullanın' using errcode = '22023';
  end if;
  select * into it from public.part_items where id = p_item for update;
  if not found then raise exception 'Parça bulunamadı' using errcode = 'P0002'; end if;
  if p_next_status = 'installed' or (p_next_status is not null and it.status = 'installed') then
    raise exception 'Takılı parçanın durumu bu fonksiyonla değiştirilemez' using errcode = '22023';
  end if;

  select * into a from public.assets where id = it.current_asset_id;
  v_part_hours := it.hours_accumulated
    + case when it.status = 'installed'
           then greatest(a.meter_hours - coalesce(it.installed_at_hours, a.meter_hours), 0) else 0 end;

  insert into public.part_events
    (tenant_id, part_item_id, event_type, asset_id, position, asset_hours, asset_km, part_hours,
     cost, reason_code, notes, performed_by)
  values
    (it.tenant_id, it.id, p_event, a.id, it.current_position, a.meter_hours, a.meter_km, v_part_hours,
     p_cost, p_reason, p_notes, app.current_user_id())
  returning * into ev;

  if p_next_status is not null then
    update public.part_items set status = p_next_status where id = it.id;
  end if;
  return ev;
end $$;

-- ---------- Görünüm: parça ikizinin canlı durumu ---------------------
-- Dashboard ve parça detay ekranı bu görünümü okur.
create or replace view public.v_part_items_live
with (security_invoker = true) as
select
  pi.id,
  pi.tenant_id,
  pi.serial_no,
  pi.qr_code,
  pi.status,
  pi.current_asset_id,
  a.code                      as asset_code,
  pi.current_position,
  p.id                        as part_id,
  p.name                      as part_name,
  p.manufacturer,
  p.part_no,
  pc.code                     as category_code,
  pc.name                     as category_name,
  -- Toplam çalışma saati: önceki montajlar + mevcut montajda geçen süre
  pi.hours_accumulated
    + case when pi.status = 'installed'
           then greatest(a.meter_hours - coalesce(pi.installed_at_hours, a.meter_hours), 0)
           else 0 end         as hours_total,
  (p.specs->>'expected_life_hours')::numeric as expected_life_hours,
  coalesce(pi.purchase_cost, 0) + coalesce(ev.extra_cost, 0) as cost_total,
  lm.latest                   as latest_measurements,
  ev.last_event_at
from public.part_items pi
join public.parts p            on p.id = pi.part_id
join public.part_categories pc on pc.id = p.category_id
left join public.assets a      on a.id = pi.current_asset_id
left join lateral (
  select sum(e.cost) as extra_cost, max(e.occurred_at) as last_event_at
    from public.part_events e where e.part_item_id = pi.id
) ev on true
left join lateral (
  select jsonb_object_agg(x.metric, jsonb_build_object('value', x.value, 'unit', x.unit, 'at', x.measured_at)) as latest
    from (
      select distinct on (ms.metric) ms.metric, ms.value, ms.unit, ms.measured_at
        from public.measurements ms
       where ms.part_item_id = pi.id
       order by ms.metric, ms.measured_at desc
    ) x
) lm on true;

grant execute on function public.record_meter_reading(uuid, numeric, numeric, app.measure_source) to sparetwin_app;
grant execute on function public.install_part_item(uuid, uuid, text, numeric, text) to sparetwin_app;
grant execute on function public.remove_part_item(uuid, text, app.part_item_status, numeric, numeric, text) to sparetwin_app;
grant execute on function public.complete_inspection(uuid) to sparetwin_app;
grant execute on function public.log_part_event(uuid, app.part_event_type, text, numeric, text, app.part_item_status) to sparetwin_app;
