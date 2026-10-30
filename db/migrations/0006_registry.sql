-- =====================================================================
-- SpareTwin — 0006: Kayıt (makine, parça, saha ekleme) desteği
-- ---------------------------------------------------------------------
-- QR kodu verilmeden eklenen makine ve parçalara otomatik, benzersiz
-- bir kod atanır. Kod yalnızca kimliktir; içinde gizli bilgi yoktur.
--   Makine: ST-A-XXXXXXXXXX   Parça: ST-P-XXXXXXXXXX
-- =====================================================================

create or replace function app.new_qr(p_prefix text)
returns text language sql volatile as $$
  select p_prefix || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10));
$$;
grant execute on function app.new_qr(text) to sparetwin_app;

alter table public.assets     alter column qr_code set default app.new_qr('ST-A-');
alter table public.part_items alter column qr_code set default app.new_qr('ST-P-');

-- Aynı firmada aynı katalog kaleminden aynı seri numarası iki kez girilmesin
create unique index part_items_serial_uq
  on public.part_items (tenant_id, part_id, serial_no) where serial_no is not null;

-- Firma içinde katalog kalemi tekrarı olmasın (üretici + parça no)
create unique index parts_tenant_partno_uq
  on public.parts (tenant_id, manufacturer, part_no)
  where tenant_id is not null and part_no is not null;
