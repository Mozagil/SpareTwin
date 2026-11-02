-- =====================================================================
-- SpareTwin — 0009: Taslak ve iptal edilmiş kontrollerin ölçümleri sayılmaz
-- ---------------------------------------------------------------------
-- Önceden, taslak bir inspeksiyonda girilen ölçüm kalite kapılarından
-- geçmeden sağlık skorlarına yansıyordu; iptal edilen kontrollerinki de.
-- Artık yalnızca tamamlanmış kontrollerin ölçümleri (ve kontrol dışı
-- kaynaklar, ör. sensör) "son ölçüm" olarak kullanılır.
-- Kolonlar aynı; bağımlı görünümler ve API etkilenmez.
-- =====================================================================

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
        left join public.inspections ins on ins.id = ms.inspection_id
       where ms.part_item_id = pi.id
         -- Yalnızca tamamlanmış kontrollerin (veya kontrol dışı, ör. sensör) ölçümleri sayılır
         and (ms.inspection_id is null or ins.status = 'completed')
       order by ms.metric, ms.measured_at desc
    ) x
) lm on true;
