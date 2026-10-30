-- =====================================================================
-- SpareTwin — 0007: Ölçümü olmayan lastiğin sağlık skoru düzeltmesi
-- ---------------------------------------------------------------------
-- Hata: Henüz diş derinliği ölçülmemiş (yeni takılmış) bir lastik %0 ve
-- "kritik" görünüyordu. PostgreSQL'de greatest(NULL, 0) = 0 olduğu için
-- eksik ölçüm sıfır gibi hesaplanıyordu. Doğrusu: ölçüm yoksa skor yok,
-- bant 'unknown' ("ölçüm bekliyor").
-- Kolonlar aynı kaldığı için bağımlı görünümler (v_part_health,
-- v_asset_health) ve API etkilenmez.
-- =====================================================================

create or replace view public.v_tire_health
with (security_invoker = true) as
select
  l.*,
  ts.size,
  ts.construction,
  ts.otd_mm,
  ts.scrap_tread_mm,
  (l.latest_measurements->'tread_depth_mm'->>'value')::numeric as tread_mm,
  (l.latest_measurements->'pressure_kpa'->>'value')::numeric   as pressure_kpa,
  -- Kalan diş yüzdesi: hurda sınırına göre
  -- Ölçüm yoksa NULL kalır (greatest() NULL'u yok sayıp 0 döndürdüğü için ayrıca kontrol)
  case when l.latest_measurements ? 'tread_depth_mm' then
    round(100 * greatest(
      ((l.latest_measurements->'tread_depth_mm'->>'value')::numeric - ts.scrap_tread_mm)
        / (ts.otd_mm - ts.scrap_tread_mm), 0), 1)
  end                                                           as tread_remaining_pct,
  -- Aşınma hızı (mm/saat) ve tahmini kalan saat (doğrusal model, Faz 1)
  case when l.hours_total > 0 then
    round((ts.otd_mm - (l.latest_measurements->'tread_depth_mm'->>'value')::numeric) / l.hours_total, 5)
  end                                                           as wear_mm_per_hour,
  case when l.hours_total > 0
        and ts.otd_mm > (l.latest_measurements->'tread_depth_mm'->>'value')::numeric then
    round(greatest((l.latest_measurements->'tread_depth_mm'->>'value')::numeric - ts.scrap_tread_mm, 0)
          / ((ts.otd_mm - (l.latest_measurements->'tread_depth_mm'->>'value')::numeric) / l.hours_total))
  end                                                           as projected_hours_left,
  case when l.hours_total > 0 then round(l.cost_total / l.hours_total, 2) end as cost_per_hour,
  -- Ömür sonunda beklenen saat başı maliyet: maliyet ÷ (çalışılan + tahmini kalan saat)
  case when l.hours_total > 0 and w.rate > 0 then
    round(l.cost_total / (l.hours_total + greatest(w.cur - ts.scrap_tread_mm, 0) / w.rate), 2)
  end                                                           as expected_cost_per_hour
from public.v_part_items_live l
join public.tire_specs ts on ts.part_id = l.part_id
cross join lateral (
  select (l.latest_measurements->'tread_depth_mm'->>'value')::numeric as cur,
         case when l.hours_total > 0
              then (ts.otd_mm - (l.latest_measurements->'tread_depth_mm'->>'value')::numeric) / l.hours_total
         end as rate
) w
where l.category_code = 'tire';
