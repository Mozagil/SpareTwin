-- =====================================================================
-- SpareTwin — Demo veri (yalnızca yerel/geliştirme ortamı)
-- `python -m sparetwin.cli seed-demo` ile yüklenir; demo kullanıcıları da
-- aynı komut oluşturur (parolalar burada değil, argon2 ile API tarafında).
-- =====================================================================

-- Sabit kimlikler: test ederken URL'lerde aynı kalsın diye.
insert into public.tenants (id, name, slug, plan, settings) values
  ('11111111-1111-1111-1111-111111111111', 'Demo Liman ve Maden A.Ş.', 'demo', 'pilot',
   '{"currency":"USD","locale":"tr-TR","thresholds":{"downtime_cost_per_hour":150}}');

insert into public.sites (id, tenant_id, name, kind, city) values
  ('21111111-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Ambarlı liman sahası', 'liman', 'İstanbul'),
  ('21111111-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Soma açık ocak', 'maden', 'Manisa');

-- Makine modelleri ortak şablonlara bağlanır
insert into public.asset_models (id, tenant_id, manufacturer, model, category, template_id)
select v.id::uuid, '11111111-1111-1111-1111-111111111111', v.mf, v.md, v.cat,
       (select id from public.position_templates where tenant_id is null and layout = v.layout)
from (values
  ('31111111-0000-0000-0000-000000000001', 'Volvo',  'L220H',  'wheel_loader',  'loader'),
  ('31111111-0000-0000-0000-000000000002', 'Kalmar', 'DRG450', 'reach_stacker', 'reach_stacker'),
  ('31111111-0000-0000-0000-000000000003', 'Linde',  'H50',    'forklift',      'forklift')
) as v(id, mf, md, cat, layout);

insert into public.assets (id, tenant_id, site_id, model_id, code, serial_no, year, meter_hours, qr_code) values
  ('41111111-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', '21111111-0000-0000-0000-000000000002',
   '31111111-0000-0000-0000-000000000001', 'LD-07', 'VCE0L220H0001', 2019, 12480, 'ST-A-LD07'),
  ('41111111-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', '21111111-0000-0000-0000-000000000002',
   '31111111-0000-0000-0000-000000000001', 'LD-09', 'VCE0L220H0002', 2022, 6210, 'ST-A-LD09'),
  ('41111111-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', '21111111-0000-0000-0000-000000000001',
   '31111111-0000-0000-0000-000000000002', 'RS-02', 'KDRG4500017', 2016, 18900, 'ST-A-RS02'),
  ('41111111-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', '21111111-0000-0000-0000-000000000001',
   '31111111-0000-0000-0000-000000000003', 'FL-14', 'LH50D0099', 2020, 9340, 'ST-A-FL14');

-- Firma kataloğu (ortak kategorilere bağlı)
insert into public.parts (id, tenant_id, category_id, manufacturer, part_no, name, specs, list_cost, min_stock)
select v.id::uuid, '11111111-1111-1111-1111-111111111111',
       (select id from public.part_categories where tenant_id is null and code = v.cat),
       v.mf, v.pn, v.nm, v.specs::jsonb, v.cost, v.min_stock
from (values
  ('51111111-0000-0000-0000-000000000001', 'tire', 'Michelin',    'XLDD2-29.5R25', '29.5R25 L-4 radyal',      '{}', 9800, 2),
  ('51111111-0000-0000-0000-000000000002', 'tire', 'Bridgestone', 'VSDL-18.00-25', '18.00-25 E-4 diyagonal',  '{}', 3200, 4),
  ('51111111-0000-0000-0000-000000000003', 'tire', 'Trelleborg',  'XP1000-7.00-12','7.00-12 dolgu lastik',    '{}', 420, 4),
  ('51111111-0000-0000-0000-000000000004', 'rim',  'Titan',       'R25-5PC',       '25x25.00/3.5 5 parça jant','{}', 2600, 1),
  ('51111111-0000-0000-0000-000000000005', 'hyd_cylinder', 'Volvo', 'VOE-LIFT-220', 'L220H kaldırma silindiri', '{"expected_life_hours":12000}', 4500, 0),
  ('51111111-0000-0000-0000-000000000006', 'hyd_cylinder', 'Volvo', 'VOE-TILT-220', 'L220H devirme silindiri',  '{"expected_life_hours":12000}', 3900, 0),
  ('51111111-0000-0000-0000-000000000007', 'hyd_pump',     'Rexroth','A10VO-140',   'Değişken deplasmanlı pompa','{"expected_life_hours":15000}', 6100, 0),
  ('51111111-0000-0000-0000-000000000008', 'hyd_cylinder', 'Kalmar', 'KB-BOOM-450', 'DRG450 bom silindiri',     '{"expected_life_hours":20000}', 8700, 0),
  ('51111111-0000-0000-0000-000000000009', 'hyd_cylinder', 'Linde',  'LM-MAST-H50', 'H50 direk silindiri',      '{"expected_life_hours":15000}', 1900, 0),
  ('51111111-0000-0000-0000-000000000010', 'battery',      'Varta',  'VB-80V-700',  '80V çekiş aküsü',           '{"expected_life_hours":10000}', 5400, 0)
) as v(id, cat, mf, pn, nm, specs, cost, min_stock);

insert into public.tire_specs (part_id, size, construction, rating, tra_code, otd_mm, scrap_tread_mm, retreadable) values
  ('51111111-0000-0000-0000-000000000001', '29.5R25', 'radial', '2*',   'L-4', 55, 8, true),
  ('51111111-0000-0000-0000-000000000002', '18.00-25','bias',   '40PR', 'E-4', 45, 6, true),
  ('51111111-0000-0000-0000-000000000003', '7.00-12', 'solid',  null,   null,  22, 5, false);

insert into public.rim_specs (part_id, size, pieces, max_pressure_kpa, ndt_interval_hours) values
  ('51111111-0000-0000-0000-000000000004', '25x25.00/3.5', 5, 650, 4000);

-- ---------- Yardımcı: takılı parça ikizi oluştur ----------------------
-- Montaj olayı, iki ölçüm (eski + güncel) ve inspeksiyon kayıtlarıyla birlikte.
create function pg_temp.seed_item(
  p_asset_code text, p_position text, p_part uuid, p_serial text,
  p_installed_at numeric, p_prev_hours numeric, p_cost numeric,
  p_metric text default null, p_prev_value numeric default null, p_value numeric default null,
  p_unit text default null
) returns uuid language plpgsql as $$
declare
  t   uuid := '11111111-1111-1111-1111-111111111111';
  a   public.assets;
  pid uuid;
  ins_old uuid; ins_new uuid;
begin
  select * into a from public.assets where code = p_asset_code and tenant_id = t;

  insert into public.part_items (tenant_id, part_id, serial_no, qr_code, status, site_id,
                                 current_asset_id, current_position, installed_at_hours,
                                 hours_accumulated, purchase_cost, acquired_at)
  values (t, p_part, p_serial, 'ST-P-' || p_serial, 'installed', a.site_id,
          a.id, p_position, p_installed_at, p_prev_hours, p_cost, current_date - 400)
  returning id into pid;

  insert into public.part_events (tenant_id, part_item_id, event_type, occurred_at, cost)
  values (t, pid, 'received', now() - interval '400 days', null);
  insert into public.part_events (tenant_id, part_item_id, event_type, asset_id, position, asset_hours, part_hours, occurred_at)
  values (t, pid, 'installed', a.id, p_position, p_installed_at, p_prev_hours, now() - interval '200 days');

  if p_metric is not null then
    -- Önceki inspeksiyon (yaklaşık 60 gün önce)
    select id into ins_old from public.inspections
     where asset_id = a.id and completed_at < now() - interval '30 days' limit 1;
    if ins_old is null then
      insert into public.inspections (tenant_id, asset_id, status, asset_hours, started_at, completed_at)
      values (t, a.id, 'completed', round(a.meter_hours - (a.meter_hours - p_installed_at) * 0.4),
              now() - interval '60 days', now() - interval '60 days')
      returning id into ins_old;
    end if;
    -- Son inspeksiyon (dün)
    select id into ins_new from public.inspections
     where asset_id = a.id and completed_at > now() - interval '30 days' limit 1;
    if ins_new is null then
      insert into public.inspections (tenant_id, asset_id, status, asset_hours, started_at, completed_at)
      values (t, a.id, 'completed', a.meter_hours, now() - interval '1 day', now() - interval '1 day')
      returning id into ins_new;
    end if;

    insert into public.measurements (tenant_id, part_item_id, inspection_id, metric, value, unit, asset_hours, measured_at)
    values
      (t, pid, ins_old, p_metric, p_prev_value, p_unit,
       (select asset_hours from public.inspections where id = ins_old), now() - interval '60 days'),
      (t, pid, ins_new, p_metric, p_value, p_unit, a.meter_hours, now() - interval '1 day');

    insert into public.part_events (tenant_id, part_item_id, event_type, asset_id, position, asset_hours, part_hours, occurred_at)
    values (t, pid, 'inspected', a.id, p_position, a.meter_hours,
            p_prev_hours + a.meter_hours - p_installed_at, now() - interval '1 day');
  end if;
  return pid;
end $$;

-- LD-07: arka lastikler sona yaklaşıyor
select pg_temp.seed_item('LD-07', 'A1-L', '51111111-0000-0000-0000-000000000001', 'MX29-0412', 10900, 0, 9800, 'tread_depth_mm', 44, 38, 'mm');
select pg_temp.seed_item('LD-07', 'A1-R', '51111111-0000-0000-0000-000000000001', 'MX29-0413', 10900, 0, 9800, 'tread_depth_mm', 42, 35, 'mm');
select pg_temp.seed_item('LD-07', 'A2-L', '51111111-0000-0000-0000-000000000001', 'MX29-0298', 10900, 2100, 9800, 'tread_depth_mm', 22, 14, 'mm');
select pg_temp.seed_item('LD-07', 'A2-R', '51111111-0000-0000-0000-000000000001', 'MX29-0301', 10900, 1800, 9800, 'tread_depth_mm', 27, 21, 'mm');
select pg_temp.seed_item('LD-07', 'LIFT-CYL-L', '51111111-0000-0000-0000-000000000005', 'VLC-88121', 0, 0, 4500, 'drift_mm', 4, 7, 'mm');
select pg_temp.seed_item('LD-07', 'LIFT-CYL-R', '51111111-0000-0000-0000-000000000005', 'VLC-88122', 7000, 0, 4500, 'drift_mm', 3, 3, 'mm');
select pg_temp.seed_item('LD-07', 'TILT-CYL',   '51111111-0000-0000-0000-000000000006', 'VTC-50310', 6200, 0, 3900);
select pg_temp.seed_item('LD-07', 'MAIN-PUMP',  '51111111-0000-0000-0000-000000000007', 'RX-140-7781', 4000, 0, 6100);

-- LD-09: genç makine, her şey iyi
select pg_temp.seed_item('LD-09', 'A1-L', '51111111-0000-0000-0000-000000000001', 'MX29-0518', 5100, 0, 9800, 'tread_depth_mm', 49, 46, 'mm');
select pg_temp.seed_item('LD-09', 'A1-R', '51111111-0000-0000-0000-000000000001', 'MX29-0519', 5100, 0, 9800, 'tread_depth_mm', 48, 45, 'mm');
select pg_temp.seed_item('LD-09', 'A2-L', '51111111-0000-0000-0000-000000000001', 'MX29-0520', 5100, 0, 9800, 'tread_depth_mm', 50, 47, 'mm');
select pg_temp.seed_item('LD-09', 'A2-R', '51111111-0000-0000-0000-000000000001', 'MX29-0521', 5100, 0, 9800, 'tread_depth_mm', 50, 46, 'mm');
select pg_temp.seed_item('LD-09', 'LIFT-CYL-L', '51111111-0000-0000-0000-000000000005', 'VLC-91002', 0, 0, 4500);
select pg_temp.seed_item('LD-09', 'LIFT-CYL-R', '51111111-0000-0000-0000-000000000005', 'VLC-91003', 0, 0, 4500);
select pg_temp.seed_item('LD-09', 'TILT-CYL',   '51111111-0000-0000-0000-000000000006', 'VTC-51877', 0, 0, 3900);
select pg_temp.seed_item('LD-09', 'MAIN-PUMP',  '51111111-0000-0000-0000-000000000007', 'RX-140-9102', 0, 0, 6100);

-- RS-02: yaşlı reach stacker, bom silindiri ömrünün sonunda
select pg_temp.seed_item('RS-02', 'A1-LO', '51111111-0000-0000-0000-000000000002', 'BS18-2201', 17200, 0, 3200, 'tread_depth_mm', 30, 24, 'mm');
select pg_temp.seed_item('RS-02', 'A1-LI', '51111111-0000-0000-0000-000000000002', 'BS18-2202', 17200, 0, 3200, 'tread_depth_mm', 29, 22, 'mm');
select pg_temp.seed_item('RS-02', 'A1-RI', '51111111-0000-0000-0000-000000000002', 'BS18-2203', 17200, 0, 3200, 'tread_depth_mm', 31, 25, 'mm');
select pg_temp.seed_item('RS-02', 'A1-RO', '51111111-0000-0000-0000-000000000002', 'BS18-2204', 17200, 0, 3200, 'tread_depth_mm', 26, 17, 'mm');
select pg_temp.seed_item('RS-02', 'A2-L',  '51111111-0000-0000-0000-000000000002', 'BS18-1987', 16100, 0, 3200, 'tread_depth_mm', 37, 33, 'mm');
select pg_temp.seed_item('RS-02', 'A2-R',  '51111111-0000-0000-0000-000000000002', 'BS18-1988', 16100, 0, 3200, 'tread_depth_mm', 38, 34, 'mm');
select pg_temp.seed_item('RS-02', 'BOOM-CYL', '51111111-0000-0000-0000-000000000008', 'KB-450-0071', 0, 0, 8700, 'drift_mm', 9, 14, 'mm');

-- FL-14: forklift, dolgu lastikler + akü
select pg_temp.seed_item('FL-14', 'A1-L', '51111111-0000-0000-0000-000000000003', 'TB7-3301', 7900, 0, 420, 'tread_depth_mm', 15, 12, 'mm');
select pg_temp.seed_item('FL-14', 'A1-R', '51111111-0000-0000-0000-000000000003', 'TB7-3302', 7900, 0, 420, 'tread_depth_mm', 15, 13, 'mm');
select pg_temp.seed_item('FL-14', 'A2-L', '51111111-0000-0000-0000-000000000003', 'TB7-3303', 7900, 0, 420, 'tread_depth_mm', 18, 16, 'mm');
select pg_temp.seed_item('FL-14', 'A2-R', '51111111-0000-0000-0000-000000000003', 'TB7-3304', 7900, 0, 420, 'tread_depth_mm', 18, 16, 'mm');
select pg_temp.seed_item('FL-14', 'MAST-CYL', '51111111-0000-0000-0000-000000000009', 'LM-H50-221', 0, 0, 1900);
select pg_temp.seed_item('FL-14', 'BATTERY',  '51111111-0000-0000-0000-000000000010', 'VB80-5512', 3000, 0, 5400, 'voltage_v', 82, 79, 'V');

-- Stokta bekleyen parçalar (değişim planlamasında kullanılır)
insert into public.part_items (tenant_id, part_id, serial_no, qr_code, status, site_id, purchase_cost, acquired_at) values
  ('11111111-1111-1111-1111-111111111111', '51111111-0000-0000-0000-000000000001', 'MX29-0601', 'ST-P-MX29-0601', 'in_stock',
   '21111111-0000-0000-0000-000000000002', 9800, current_date - 20),
  ('11111111-1111-1111-1111-111111111111', '51111111-0000-0000-0000-000000000002', 'BS18-2290', 'ST-P-BS18-2290', 'in_stock',
   '21111111-0000-0000-0000-000000000001', 3200, current_date - 45),
  ('11111111-1111-1111-1111-111111111111', '51111111-0000-0000-0000-000000000004', 'TR25-0107', 'ST-P-TR25-0107', 'in_stock',
   '21111111-0000-0000-0000-000000000002', 2600, current_date - 90);

-- Bir parçanın tamir maliyeti (saat başı maliyete yansır)
insert into public.part_events (tenant_id, part_item_id, event_type, cost, reason_code, notes, occurred_at)
select tenant_id, id, 'repaired', 650, 'seal_leak', 'Keçe takımı değişti', now() - interval '35 days'
  from public.part_items where serial_no = 'KB-450-0071';

-- ---------- Jantlar (NDT muayene periyodu 4.000 saat) ----------
-- Her durumdan bir örnek: gecikmiş, yaklaşan, güncel.
create function pg_temp.seed_rim(p_asset text, p_pos text, p_serial text, p_ndt_part_hours numeric, p_days_ago int)
returns void language plpgsql as $$
declare
  t   uuid := '11111111-1111-1111-1111-111111111111';
  pid uuid;
begin
  pid := pg_temp.seed_item(p_asset, p_pos, '51111111-0000-0000-0000-000000000004', p_serial, 0, 0, 2600);
  if p_ndt_part_hours is not null then
    insert into public.part_events (tenant_id, part_item_id, event_type, reason_code, part_hours, notes, occurred_at)
    values (t, pid, 'inspected', 'ndt', p_ndt_part_hours, 'NDT: çatlak bulunmadı', now() - make_interval(days => p_days_ago));
  end if;
end $$;

select pg_temp.seed_rim('LD-07', 'A1-L-J', 'TR25-0151', null,  0);    -- hiç muayene yok → gecikmiş
select pg_temp.seed_rim('LD-07', 'A1-R-J', 'TR25-0152', 8800,  210);  -- 3.680 saat önce → yaklaşıyor
select pg_temp.seed_rim('LD-07', 'A2-L-J', 'TR25-0153', 11000, 70);   -- güncel
select pg_temp.seed_rim('LD-07', 'A2-R-J', 'TR25-0154', 10500, 95);   -- güncel
select pg_temp.seed_rim('LD-09', 'A1-L-J', 'TR25-0161', 3000,  150);
select pg_temp.seed_rim('LD-09', 'A1-R-J', 'TR25-0162', 3000,  150);
select pg_temp.seed_rim('LD-09', 'A2-L-J', 'TR25-0163', 3000,  150);
select pg_temp.seed_rim('LD-09', 'A2-R-J', 'TR25-0164', 3000,  150);

-- ---------- Sarf malzemeleri ve stok hareketleri (Faz 2) ----------
insert into public.parts (id, tenant_id, category_id, manufacturer, part_no, name, specs, list_cost, min_stock, unit)
select v.id::uuid, '11111111-1111-1111-1111-111111111111',
       (select id from public.part_categories where tenant_id is null and code = v.cat),
       v.mf, v.pn, v.nm, '{}'::jsonb, v.cost, v.min_stock, v.unit
from (values
  ('51111111-0000-0000-0000-000000000011', 'filter',    'Volvo',  'VOE-11110683', 'L220H hidrolik filtresi',  85.00, 6,   'adet'),
  ('51111111-0000-0000-0000-000000000012', 'lubricant', 'Shell',  'RIMULA-R4-15W40', 'Motor yağı 15W-40',      4.20, 200, 'litre'),
  ('51111111-0000-0000-0000-000000000013', 'seal_kit',  'Volvo',  'VOE-SK-LIFT220', 'L220H kaldırma silindiri keçe takımı', 340.00, 2, 'takım')
) as v(id, cat, mf, pn, nm, cost, min_stock, unit);

insert into public.stock_movements (tenant_id, part_id, site_id, kind, qty, unit_cost, asset_id, reason, ref, occurred_at)
select '11111111-1111-1111-1111-111111111111', v.part::uuid, v.site::uuid, v.kind::app.stock_move_kind, v.qty, v.cost,
       (select id from public.assets where code = v.asset), v.reason, v.ref, now() - make_interval(days => v.days)
from (values
  -- Soma deposu
  ('51111111-0000-0000-0000-000000000011', '21111111-0000-0000-0000-000000000002', 'in',  12,   82.00, null,    'satınalma', 'IRS-2026-0811', 90),
  ('51111111-0000-0000-0000-000000000011', '21111111-0000-0000-0000-000000000002', 'out', -4,   82.00, 'LD-07', 'periyodik bakım', null, 60),
  ('51111111-0000-0000-0000-000000000011', '21111111-0000-0000-0000-000000000002', 'out', -4,   82.00, 'LD-09', 'periyodik bakım', null, 20),
  ('51111111-0000-0000-0000-000000000012', '21111111-0000-0000-0000-000000000002', 'in',  400,  4.05,  null,    'satınalma', 'IRS-2026-0790', 100),
  ('51111111-0000-0000-0000-000000000012', '21111111-0000-0000-0000-000000000002', 'out', -60,  4.05,  'LD-07', 'yağ değişimi', null, 60),
  ('51111111-0000-0000-0000-000000000012', '21111111-0000-0000-0000-000000000002', 'out', -60,  4.05,  'LD-09', 'yağ değişimi', null, 20),
  ('51111111-0000-0000-0000-000000000013', '21111111-0000-0000-0000-000000000002', 'in',  2,    340.00, null,   'satınalma', 'IRS-2026-0741', 120),
  ('51111111-0000-0000-0000-000000000013', '21111111-0000-0000-0000-000000000002', 'out', -1,   340.00, 'LD-07', 'silindir tamiri', null, 35),
  -- Ambarlı deposu
  ('51111111-0000-0000-0000-000000000012', '21111111-0000-0000-0000-000000000001', 'in',  120,  4.30,  null,    'satınalma', 'IRS-2026-0802', 80),
  ('51111111-0000-0000-0000-000000000012', '21111111-0000-0000-0000-000000000001', 'out', -40,  4.30,  'RS-02', 'yağ değişimi', null, 30)
) as v(part, site, kind, qty, cost, asset, reason, ref, days);

-- ---------- Satınalma (Faz 2) ----------
insert into public.suppliers (id, tenant_id, name, contact_name, phone, email, lead_time_days, notes) values
  ('61111111-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Volvo Yetkili Servis',
   'Ahmet Kaya', '+90 232 000 00 01', 'servis@volvo-bayi.test', 7, 'Filtre, keçe ve silindir parçaları'),
  ('61111111-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Lastik Dünyası (Michelin bayisi)',
   'Elif Demir', '+90 236 000 00 02', 'satis@lastikdunyasi.test', 14, '29.5R25 ve 18.00-25 ebatları stoktan');

-- Açık sipariş: filtre ve keçe takımı yolda (teslim 4 gün sonra)
insert into public.purchase_orders (id, tenant_id, number, supplier_id, site_id, status, expected_at, notes, requested_by, ordered_by, ordered_at, created_at)
values ('71111111-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'SA-' || to_char(now(), 'YYYY') || '-0001',
        '61111111-0000-0000-0000-000000000001', '21111111-0000-0000-0000-000000000002', 'ordered', current_date + 4,
        'Periyodik bakım stoğu', (select id from public.app_users where email = 'teknisyen@demo.sparetwin.dev'),
        (select id from public.app_users where email = 'yonetici@demo.sparetwin.dev'), now() - interval '3 days', now() - interval '4 days');
insert into public.purchase_order_lines (tenant_id, order_id, part_id, qty, unit_cost) values
  ('11111111-1111-1111-1111-111111111111', '71111111-0000-0000-0000-000000000001', '51111111-0000-0000-0000-000000000011', 10, 84.00),
  ('11111111-1111-1111-1111-111111111111', '71111111-0000-0000-0000-000000000001', '51111111-0000-0000-0000-000000000013', 1, 335.00);

-- ---------- Bakım planları ve iş emirleri (Faz 2) ----------
-- L220H modelinin tüm makineleri için 500 saat bakımı; RS-02 için 6 aylık takvim bakımı.
insert into public.maintenance_plans (id, tenant_id, name, model_id, interval_hours, checklist, notes, created_by, created_at) values
  ('81111111-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', '500 saat periyodik bakım',
   '31111111-0000-0000-0000-000000000001', 500,
   '["Hidrolik filtre değişimi", "Motor yağı değişimi", "Gresleme", "Lastik basınç ve diş kontrolü"]',
   'Volvo L220H servis kitabı, 500 saat tablosu',
   (select id from public.app_users where email = 'yonetici@demo.sparetwin.dev'), now() - interval '200 days');
insert into public.maintenance_plans (id, tenant_id, name, asset_id, interval_days, checklist, created_by, created_at) values
  ('81111111-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', '6 aylık hidrolik sistem bakımı',
   '41111111-0000-0000-0000-000000000003', 180,
   '["Hortum ve bağlantı kontrolü", "Hidrolik yağ analizi", "Bom silindiri keçe kontrolü"]',
   (select id from public.app_users where email = 'yonetici@demo.sparetwin.dev'), now() - interval '175 days');
insert into public.maintenance_plan_parts (tenant_id, plan_id, part_id, qty) values
  ('11111111-1111-1111-1111-111111111111', '81111111-0000-0000-0000-000000000001', '51111111-0000-0000-0000-000000000011', 4),
  ('11111111-1111-1111-1111-111111111111', '81111111-0000-0000-0000-000000000001', '51111111-0000-0000-0000-000000000012', 60);

-- Tamamlanmış emirler: LD-07 12.000 saatte (60 gün önce), LD-09 6.000 saatte (20 gün önce); stok çıkışları yukarıda.
insert into public.work_orders (id, tenant_id, number, asset_id, plan_id, kind, status, title, due_hours, asset_hours_at_done, labor_cost,
                                created_by, completed_by, started_at, completed_at, created_at)
select v.id::uuid, '11111111-1111-1111-1111-111111111111', 'BK-' || to_char(now(), 'YYYY') || '-' || v.no, v.asset::uuid,
       '81111111-0000-0000-0000-000000000001', 'planned', 'done', '500 saat periyodik bakım', v.hours, v.hours, 250,
       (select id from public.app_users where email = 'teknisyen@demo.sparetwin.dev'),
       (select id from public.app_users where email = 'teknisyen@demo.sparetwin.dev'),
       now() - make_interval(days => v.days, hours => 3), now() - make_interval(days => v.days), now() - make_interval(days => v.days + 2)
from (values
  ('91111111-0000-0000-0000-000000000001', '0001', '41111111-0000-0000-0000-000000000001', 12000, 60),
  ('91111111-0000-0000-0000-000000000002', '0002', '41111111-0000-0000-0000-000000000002', 6000,  20)
) as v(id, no, asset, hours, days);
insert into public.work_order_parts (tenant_id, work_order_id, part_id, qty, site_id, unit_cost)
select '11111111-1111-1111-1111-111111111111', w::uuid, p::uuid, q, '21111111-0000-0000-0000-000000000002', c
from (values
  ('91111111-0000-0000-0000-000000000001', '51111111-0000-0000-0000-000000000011', 4,  82.00),
  ('91111111-0000-0000-0000-000000000001', '51111111-0000-0000-0000-000000000012', 60, 4.05),
  ('91111111-0000-0000-0000-000000000002', '51111111-0000-0000-0000-000000000011', 4,  82.00),
  ('91111111-0000-0000-0000-000000000002', '51111111-0000-0000-0000-000000000012', 60, 4.05)
) as v(w, p, q, c);

-- Kapanmış arıza: FL-14 direk silindiri kaçağı, 5 saat duruş (10 gün önce)
insert into public.work_orders (id, tenant_id, number, asset_id, kind, status, title, description, down_from, down_to, reason_code,
                                labor_cost, external_cost, asset_hours_at_done, created_by, completed_by, started_at, completed_at, created_at)
values ('91111111-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'BK-' || to_char(now(), 'YYYY') || '-0003',
        '41111111-0000-0000-0000-000000000004', 'breakdown', 'done', 'Direk silindiri yağ kaçağı',
        'Keçe değişti, hidrolik yağ tamamlandı.', now() - interval '10 days 5 hours', now() - interval '10 days', 'hydraulic',
        180, 0, 9300,
        (select id from public.app_users where email = 'teknisyen@demo.sparetwin.dev'),
        (select id from public.app_users where email = 'teknisyen@demo.sparetwin.dev'),
        now() - interval '10 days 4 hours', now() - interval '10 days', now() - interval '10 days 5 hours');

-- ---------- Maliyet raporu (TCO) için sayaç geçmişi ----------
-- Bir yıl önceki sayaç okumaları: son 12 ayın çalışma saati ve saat başı maliyet buradan çıkar.
-- Duruş saat maliyeti (150 $/saat) firma ayarında, en üstte.
insert into public.meter_readings (tenant_id, asset_id, hours, source, read_at)
select '11111111-1111-1111-1111-111111111111', a.id, v.hours, 'manual', now() - interval '370 days'
  from (values ('LD-07', 9600), ('LD-09', 3400), ('RS-02', 15800), ('FL-14', 6900)) as v(code, hours)
  join public.assets a on a.code = v.code and a.tenant_id = '11111111-1111-1111-1111-111111111111';
