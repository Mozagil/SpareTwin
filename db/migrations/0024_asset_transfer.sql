-- =====================================================================
-- SpareTwin — 0024: Makine ikizini başka firmaya devretme
-- ---------------------------------------------------------------------
-- Üretici teslim ettiği makinenin ikizini müşterisine devreder: makine,
-- üzerinde takılı parça ikizleri ve bunların geçmişi (olay defteri,
-- ölçümler, kontroller, fotoğraflar, sayaç okumaları) alıcı firmaya
-- TAŞINIR. Kopya çıkmaz: fiziksel makine tek olduğu için ikiz de tektir,
-- QR etiketleri aynı kalır.
--
-- Akış (iki tarafın da onayı):
--   asset_transfer_create  → devreden firma tek kullanımlık kod üretir
--                            (DV-XXXXXXXXXX, 30 gün geçerli)
--   asset_transfer_preview → alıcı kodu girer, ne alacağını görür
--   asset_transfer_accept  → alıcı filo kodunu ve sahayı seçip devralır
--   asset_transfer_cancel  → devreden, kabul edilmemiş devri iptal eder
--
-- Firmalar birbirini göremediği için (RLS) bu dört fonksiyon tabloların
-- sahibi yetkisiyle çalışır (SECURITY DEFINER) ve yetkiyi kendi denetler.
-- asset_transfers tablosuna API rolü yalnızca okuma yapar.
--
-- Devralırken:
--   - Devredene özel katalog kalemi, parça tipi, makine modeli ve pozisyon
--     şablonu alıcıda yoksa kopyalanır; varsa (aynı üretici + parça no,
--     aynı model adı ve yuvalar) alıcınınki kullanılır.
--   - Maliyet geçmez: parça alış fiyatı, olay maliyeti ve liste fiyatı
--     boşaltılır; makineye özel duruş oranı sıfırlanır.
--   - Her parçaya 'transferred' olayı yazılır.
--   - Devredenin iş emirleri, stok hareketleri ve satınalma kayıtları
--     kendisinde kalır; makineye bağlı bakım planları pasifleşir.
-- Açık iş emri ya da taslak kontrol varken makine devredilemez.
-- =====================================================================

create table public.asset_transfers (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references public.tenants(id) on delete cascade,   -- devreden firma
  asset_id          uuid references public.assets(id) on delete set null,
  code              text not null unique default app.new_qr('DV-'),
  status            text not null default 'pending' check (status in ('pending', 'accepted', 'cancelled')),
  note              text check (note is null or length(note) <= 300),               -- kime, hangi teslimat
  -- Makine alıcıya geçince devreden onu göremez; liste için özet burada durur
  asset_code        text not null,
  serial_no         text,
  model_name        text,
  part_count        integer not null default 0,
  from_tenant_name  text not null,
  to_tenant_id      uuid references public.tenants(id) on delete set null,
  to_tenant_name    text,
  created_by        uuid references public.app_users(id) on delete set null,
  created_at        timestamptz not null default now(),
  expires_at        timestamptz not null default now() + interval '30 days',
  accepted_by       uuid references public.app_users(id) on delete set null,
  accepted_at       timestamptz,
  cancelled_at      timestamptz
);
-- Bir makine için aynı anda tek bekleyen devir
create unique index asset_transfers_one_pending
  on public.asset_transfers (asset_id) where status = 'pending';
create index on public.asset_transfers (tenant_id, created_at desc);
create index on public.asset_transfers (to_tenant_id) where to_tenant_id is not null;

alter table public.asset_transfers enable row level security;
grant select on public.asset_transfers to sparetwin_app;   -- yazma yalnızca aşağıdaki fonksiyonlarla
-- Devreden tarafta kod göründüğü için yönetici ve üstü; alıcı tarafta tüm üyeler
create policy asset_transfers_select on public.asset_transfers for select to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin,manager}')
         or (to_tenant_id is not null and app.is_member(to_tenant_id)));

-- ---------- Devre engel durumlar ----------
create or replace function app.asset_transfer_blockers(p_asset uuid)
returns void
language plpgsql stable
set search_path = public, app
as $$
begin
  if exists (select 1 from public.work_orders
              where asset_id = p_asset and status in ('open', 'in_progress')) then
    raise exception 'Makinede açık iş emri var; devirden önce tamamlanmalı ya da iptal edilmeli'
      using errcode = '22023';
  end if;
  if exists (select 1 from public.inspections where asset_id = p_asset and status = 'draft') then
    raise exception 'Makinede tamamlanmamış kontrol var; devirden önce tamamlanmalı ya da iptal edilmeli'
      using errcode = '22023';
  end if;
end $$;

-- ---------- Parça tipini alıcı firmada bul ya da kopyala ----------
create or replace function app.asset_transfer_category(p_category uuid, p_tenant uuid)
returns uuid
language plpgsql
set search_path = public, app
as $$
declare
  c    public.part_categories;
  v_id uuid;
begin
  select * into c from public.part_categories where id = p_category;
  if c.tenant_id is null then
    return c.id;   -- ortak kütüphane
  end if;
  select x.id into v_id
    from public.part_categories x
   where x.code = c.code and (x.tenant_id = p_tenant or x.tenant_id is null)
   order by x.tenant_id nulls last
   limit 1;
  if v_id is null then
    insert into public.part_categories
      (tenant_id, code, name, is_serialized, measurement_profile, required_photo_angles)
    values (p_tenant, c.code, c.name, c.is_serialized, c.measurement_profile, c.required_photo_angles)
    returning id into v_id;
  end if;
  return v_id;
end $$;

revoke all on function app.asset_transfer_blockers(uuid) from public;
revoke all on function app.asset_transfer_category(uuid, uuid) from public;

-- ---------- Devir başlat ----------
create or replace function public.asset_transfer_create(p_asset uuid, p_note text default null)
returns public.asset_transfers
language plpgsql security definer
set search_path = public, app
as $$
declare
  a public.assets;
  t public.asset_transfers;
begin
  select * into a from public.assets where id = p_asset for update;
  if not found or not app.is_member(a.tenant_id) then
    raise exception 'Makine bulunamadı' using errcode = 'P0002';
  end if;
  if not app.has_role(a.tenant_id, '{owner,admin,manager}') then
    raise exception 'Bu işlem için yetkiniz yok' using errcode = '42501';
  end if;
  perform app.asset_transfer_blockers(a.id);

  -- Süresi dolmuş bekleyen devir kendiliğinden kapanır
  update public.asset_transfers set status = 'cancelled', cancelled_at = now()
   where asset_id = a.id and status = 'pending' and expires_at <= now();
  if exists (select 1 from public.asset_transfers where asset_id = a.id and status = 'pending') then
    raise exception 'Bu makine için bekleyen bir devir var' using errcode = '23505';
  end if;

  insert into public.asset_transfers
    (tenant_id, asset_id, note, asset_code, serial_no, model_name, part_count, from_tenant_name, created_by)
  values
    (a.tenant_id, a.id, nullif(trim(p_note), ''), a.code, a.serial_no,
     (select am.manufacturer || ' ' || am.model from public.asset_models am where am.id = a.model_id),
     (select count(*) from public.part_items pi where pi.current_asset_id = a.id and pi.status = 'installed'),
     (select name from public.tenants where id = a.tenant_id),
     app.current_user_id())
  returning * into t;
  return t;
end $$;

-- ---------- Devir iptal ----------
create or replace function public.asset_transfer_cancel(p_transfer uuid)
returns public.asset_transfers
language plpgsql security definer
set search_path = public, app
as $$
declare
  t public.asset_transfers;
begin
  select * into t from public.asset_transfers where id = p_transfer for update;
  if not found or not app.has_role(t.tenant_id, '{owner,admin,manager}') then
    raise exception 'Devir bulunamadı' using errcode = 'P0002';
  end if;
  if t.status <> 'pending' then
    raise exception 'Yalnızca bekleyen devir iptal edilebilir' using errcode = '22023';
  end if;
  update public.asset_transfers set status = 'cancelled', cancelled_at = now()
   where id = t.id
  returning * into t;
  return t;
end $$;

-- ---------- Alıcı: kodla önizleme ----------
create or replace function public.asset_transfer_preview(p_code text, p_tenant uuid)
returns jsonb
language plpgsql stable security definer
set search_path = public, app
as $$
declare
  t public.asset_transfers;
  a public.assets;
begin
  if not app.has_role(p_tenant, '{owner,admin,manager}') then
    raise exception 'Bu işlem için yetkiniz yok' using errcode = '42501';
  end if;
  select * into t from public.asset_transfers where code = upper(trim(p_code));
  if not found or t.status <> 'pending' or t.expires_at <= now() or t.asset_id is null then
    raise exception 'Devir kodu geçersiz ya da süresi dolmuş' using errcode = 'P0002';
  end if;
  if t.tenant_id = p_tenant then
    raise exception 'Bu devri kendi firmanız başlattı; kodu makineyi alacak firma girer' using errcode = '22023';
  end if;
  select * into a from public.assets where id = t.asset_id and tenant_id = t.tenant_id;
  if not found then
    raise exception 'Devir kodu geçersiz ya da süresi dolmuş' using errcode = 'P0002';
  end if;

  return jsonb_build_object(
    'code', t.code,
    'from_tenant_name', t.from_tenant_name,
    'note', t.note,
    'expires_at', t.expires_at,
    'asset_code', a.code,
    'serial_no', a.serial_no,
    'year', a.year,
    'meter_hours', a.meter_hours,
    'qr_code', a.qr_code,
    'model_name', (select am.manufacturer || ' ' || am.model from public.asset_models am where am.id = a.model_id),
    'code_taken', exists (select 1 from public.assets x where x.tenant_id = p_tenant and x.code = a.code),
    'parts', coalesce((
      select jsonb_agg(jsonb_build_object(
               'position', pi.current_position, 'name', p.name, 'serial_no', pi.serial_no,
               'category_code', pc.code, 'category_name', pc.name,
               'hours_total', pi.hours_accumulated
                              + greatest(a.meter_hours - coalesce(pi.installed_at_hours, a.meter_hours), 0))
             order by pi.current_position)
        from public.part_items pi
        join public.parts p on p.id = pi.part_id
        join public.part_categories pc on pc.id = p.category_id
       where pi.current_asset_id = a.id and pi.status = 'installed'), '[]'::jsonb));
end $$;

-- ---------- Alıcı: devral ----------
create or replace function public.asset_transfer_accept(
  p_code       text,
  p_tenant     uuid,
  p_asset_code text default null,
  p_site       uuid default null
) returns jsonb
language plpgsql security definer
set search_path = public, app
as $$
declare
  t          public.asset_transfers;
  a          public.assets;
  m          public.asset_models;
  r          record;
  src        uuid;
  v_from     text;
  v_to       text;
  v_code     text;
  v_items    uuid[];
  v_insp     uuid[];
  v_cat      uuid;
  v_part     uuid;
  v_map      jsonb := '{}'::jsonb;   -- devredenin katalog kalemi → alıcının katalog kalemi
  v_model    uuid;
  v_template uuid;
  v_copied   jsonb := '[]'::jsonb;   -- kopyalanan model / şablon (görselleri API çoğaltır)
  v_clash    text;
begin
  if not app.has_role(p_tenant, '{owner,admin,manager}') then
    raise exception 'Bu işlem için yetkiniz yok' using errcode = '42501';
  end if;

  select * into t from public.asset_transfers where code = upper(trim(p_code)) for update;
  if not found or t.status <> 'pending' or t.expires_at <= now() or t.asset_id is null then
    raise exception 'Devir kodu geçersiz ya da süresi dolmuş' using errcode = 'P0002';
  end if;
  if t.tenant_id = p_tenant then
    raise exception 'Bu devri kendi firmanız başlattı; kodu makineyi alacak firma girer' using errcode = '22023';
  end if;
  src := t.tenant_id;

  select * into a from public.assets where id = t.asset_id and tenant_id = src for update;
  if not found then
    raise exception 'Devir kodu geçersiz ya da süresi dolmuş' using errcode = 'P0002';
  end if;
  perform app.asset_transfer_blockers(a.id);

  v_code := coalesce(nullif(trim(p_asset_code), ''), a.code);
  if exists (select 1 from public.assets where tenant_id = p_tenant and code = v_code) then
    raise exception 'Filonuzda % kodlu bir makine var; başka bir kod girin', v_code using errcode = '23505';
  end if;
  if p_site is not null and not exists (select 1 from public.sites where id = p_site and tenant_id = p_tenant) then
    raise exception 'Saha bulunamadı' using errcode = 'P0002';
  end if;

  select name into v_from from public.tenants where id = src;
  select name into v_to from public.tenants where id = p_tenant;
  select coalesce(array_agg(id), '{}') into v_items
    from public.part_items where current_asset_id = a.id and status = 'installed';
  select coalesce(array_agg(id), '{}') into v_insp
    from public.inspections where asset_id = a.id;

  -- 1) Katalog: devredene özel kalemler alıcıda bulunur ya da kopyalanır
  for r in
    select p.* from public.parts p
     where p.tenant_id is not null
       and p.id in (select part_id from public.part_items where id = any (v_items))
  loop
    v_cat := app.asset_transfer_category(r.category_id, p_tenant);
    if r.part_no is not null then
      select x.id into v_part from public.parts x
       where x.tenant_id = p_tenant and x.part_no = r.part_no
         and x.manufacturer is not distinct from r.manufacturer
       limit 1;
    else
      select x.id into v_part from public.parts x
       where x.tenant_id = p_tenant and x.category_id = v_cat and x.part_no is null
         and lower(x.name) = lower(r.name) and x.manufacturer is not distinct from r.manufacturer
       limit 1;
    end if;
    if v_part is null then
      insert into public.parts (tenant_id, category_id, manufacturer, part_no, name, specs, unit)
      values (p_tenant, v_cat, r.manufacturer, r.part_no, r.name, r.specs, r.unit)
      returning id into v_part;
      insert into public.tire_specs
        select (jsonb_populate_record(null::public.tire_specs,
                                      to_jsonb(ts) || jsonb_build_object('part_id', v_part))).*
          from public.tire_specs ts where ts.part_id = r.id;
      insert into public.rim_specs
        select (jsonb_populate_record(null::public.rim_specs,
                                      to_jsonb(rs) || jsonb_build_object('part_id', v_part))).*
          from public.rim_specs rs where rs.part_id = r.id;
    end if;
    v_map := v_map || jsonb_build_object(r.id::text, v_part);
  end loop;

  -- Alıcıda aynı kalemden aynı seri numarası varsa taşıma yarıda kalmasın
  select string_agg(pi.serial_no, ', ') into v_clash
    from public.part_items pi
   where pi.id = any (v_items) and pi.serial_no is not null
     and exists (select 1 from public.part_items x
                  where x.tenant_id = p_tenant and x.serial_no = pi.serial_no
                    and x.part_id = coalesce((v_map ->> pi.part_id::text)::uuid, pi.part_id));
  if v_clash is not null then
    raise exception 'Filonuzda aynı seri numaralı parça var: %', v_clash using errcode = '23505';
  end if;

  -- 2) Model ve şablon
  v_model := a.model_id;
  if a.model_id is not null then
    select * into m from public.asset_models where id = a.model_id;
    if m.tenant_id is not null then
      -- Alıcıda aynı adlı model, takılı parçaların yuvalarını karşılıyorsa o kullanılır
      select x.id into v_model
        from public.asset_models x
       where x.tenant_id = p_tenant
         and lower(x.manufacturer) = lower(m.manufacturer) and lower(x.model) = lower(m.model)
         and not exists (
               select 1 from public.part_items pi
                 join public.parts p on p.id = pi.part_id
                 join public.part_categories pc on pc.id = p.category_id
                where pi.id = any (v_items)
                  and not exists (select 1 from public.template_positions tp
                                   where tp.template_id = x.template_id
                                     and tp.code = pi.current_position and tp.category_code = pc.code))
       order by x.created_at
       limit 1;
      if v_model is null then
        v_template := m.template_id;
        if exists (select 1 from public.position_templates
                    where id = m.template_id and tenant_id is not null) then
          insert into public.position_templates (tenant_id, name, layout)
          select p_tenant, name, layout from public.position_templates where id = m.template_id
          returning id into v_template;
          insert into public.template_positions (template_id, code, label, category_code, axle, x, y, sort_order)
          select v_template, code, label, category_code, axle, x, y, sort_order
            from public.template_positions where template_id = m.template_id;
          -- Boş yuvaların parça tipi de alıcıda tanımlı olsun
          perform app.asset_transfer_category(pc.id, p_tenant)
             from public.part_categories pc
            where pc.tenant_id = src
              and pc.code in (select category_code from public.template_positions where template_id = m.template_id);
          v_copied := v_copied || jsonb_build_array(jsonb_build_object(
            'entity_type', 'position_template', 'to', v_template,
            'image', (select jsonb_build_object('storage_key', at.storage_key, 'mime_type', at.mime_type,
                                                'file_name', at.file_name, 'size_bytes', at.size_bytes)
                        from public.attachments at
                       where at.tenant_id = src and at.entity_type = 'position_template'
                         and at.entity_id = m.template_id and at.kind = 'image')));
        end if;
        insert into public.asset_models (tenant_id, manufacturer, model, category, template_id)
        values (p_tenant, m.manufacturer, m.model, m.category, v_template)
        returning id into v_model;
        v_copied := v_copied || jsonb_build_array(jsonb_build_object(
          'entity_type', 'asset_model', 'to', v_model,
          'image', (select jsonb_build_object('storage_key', at.storage_key, 'mime_type', at.mime_type,
                                              'file_name', at.file_name, 'size_bytes', at.size_bytes)
                      from public.attachments at
                     where at.tenant_id = src and at.entity_type = 'asset_model'
                       and at.entity_id = m.id and at.kind = 'image')));
      end if;
    end if;
  end if;

  -- 3) Taşıma: makine, takılı parçalar ve geçmişleri
  update public.assets
     set tenant_id = p_tenant, site_id = p_site, code = v_code, model_id = v_model,
         downtime_cost_per_hour = null
   where id = a.id;
  update public.part_items
     set tenant_id = p_tenant, site_id = p_site, purchase_cost = null,
         part_id = coalesce((v_map ->> part_id::text)::uuid, part_id)
   where id = any (v_items);
  update public.part_events  set tenant_id = p_tenant, cost = null where part_item_id = any (v_items);
  update public.measurements set tenant_id = p_tenant where part_item_id = any (v_items);
  update public.inspections  set tenant_id = p_tenant where id = any (v_insp);
  update public.meter_readings set tenant_id = p_tenant where asset_id = a.id;
  update public.attachments set tenant_id = p_tenant
   where tenant_id = src
     and ((entity_type = 'asset' and entity_id = a.id)
          or part_item_id = any (v_items)
          or (entity_type = 'part_item' and entity_id = any (v_items))
          or (entity_type = 'inspection' and entity_id = any (v_insp)));
  -- Devredende makineye bağlı bakım planı artık üretmez
  update public.maintenance_plans set is_active = false where tenant_id = src and asset_id = a.id;

  -- 4) Parça geçmişine devir olayı
  insert into public.part_events
    (tenant_id, part_item_id, event_type, asset_id, position, asset_hours, asset_km, part_hours, notes, performed_by)
  select p_tenant, pi.id, 'transferred', a.id, pi.current_position, a.meter_hours, a.meter_km,
         pi.hours_accumulated + greatest(a.meter_hours - coalesce(pi.installed_at_hours, a.meter_hours), 0),
         format('Makine devri: %s → %s', v_from, v_to), app.current_user_id()
    from public.part_items pi
   where pi.id = any (v_items);

  update public.asset_transfers
     set status = 'accepted', to_tenant_id = p_tenant, to_tenant_name = v_to,
         accepted_by = app.current_user_id(), accepted_at = now(),
         part_count = cardinality(v_items)
   where id = t.id;

  return jsonb_build_object(
    'transfer_id', t.id, 'asset_id', a.id, 'asset_code', v_code, 'part_count', cardinality(v_items),
    'from_tenant_name', v_from, 'copied', v_copied);
end $$;

revoke all on function public.asset_transfer_create(uuid, text) from public;
revoke all on function public.asset_transfer_cancel(uuid) from public;
revoke all on function public.asset_transfer_preview(text, uuid) from public;
revoke all on function public.asset_transfer_accept(text, uuid, text, uuid) from public;
grant execute on function public.asset_transfer_create(uuid, text) to sparetwin_app;
grant execute on function public.asset_transfer_cancel(uuid) to sparetwin_app;
grant execute on function public.asset_transfer_preview(text, uuid) to sparetwin_app;
grant execute on function public.asset_transfer_accept(text, uuid, text, uuid) to sparetwin_app;
