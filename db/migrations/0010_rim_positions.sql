-- =====================================================================
-- SpareTwin — 0010: Jant pozisyonları
-- ---------------------------------------------------------------------
-- Her lastik bir jantın üzerinde durur. Ortak kütüphanedeki şablonlarda
-- her lastik pozisyonunun yanına bir jant pozisyonu eklenir:
--   A1-L (lastik) → A1-L-J (jant)
-- x/y boş bırakılır: jant şemada çizilmez (lastikle üst üste biner),
-- pozisyon tablosunda ve jant uyumluluk ekranında görünür.
-- Ayrıca makine özetine "ölçümü olmayan parça" sayısı eklenir; filo
-- şeridi bunları yeşil değil gri gösterir.
-- =====================================================================

insert into public.template_positions (template_id, code, label, category_code, axle, x, y, sort_order)
select tp.template_id, tp.code || '-J', tp.label || ' jantı', 'rim', tp.axle, null, null, tp.sort_order + 50
  from public.template_positions tp
  join public.position_templates pt on pt.id = tp.template_id
 where pt.tenant_id is null and tp.category_code = 'tire'
on conflict (template_id, code) do nothing;

create or replace view public.v_asset_health
with (security_invoker = true) as
select
  a.id, a.tenant_id, a.code, a.status, a.meter_hours, a.site_id,
  am.manufacturer, am.model, am.category, pt.layout,
  count(ph.id)                                   as installed_parts,
  count(*) filter (where ph.band = 'critical')   as critical_parts,
  count(*) filter (where ph.band = 'watch')      as watch_parts,
  min(ph.condition_pct)                          as worst_condition_pct,
  (select max(i.completed_at) from public.inspections i
    where i.asset_id = a.id and i.status = 'completed') as last_inspection_at,
  count(*) filter (where ph.band = 'unknown')    as unknown_parts
from public.assets a
left join public.asset_models am       on am.id = a.model_id
left join public.position_templates pt on pt.id = am.template_id
left join public.v_part_health ph      on ph.current_asset_id = a.id and ph.status = 'installed'
group by a.id, am.manufacturer, am.model, am.category, pt.layout;
