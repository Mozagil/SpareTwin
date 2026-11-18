-- =====================================================================
-- SpareTwin — 0018: Pozisyon şablonuna arka plan resmi
-- ---------------------------------------------------------------------
-- Hazır gövde çizimleri (yükleyici, reach stacker, forklift) her makineye
-- uymaz. Firma kendi şablonuna makinenin üstten fotoğrafını ya da teknik
-- çizimini yükler; yuvalar onun üzerine yerleştirilir ve makine şeması bu
-- resmin üzerinde çizilir. Resim, diğer görseller gibi attachments'ta
-- kind = 'image' olarak durur (firma başına kayıt başına tek görsel, 0008).
-- =====================================================================

alter table public.attachments drop constraint attachments_entity_type_check;
alter table public.attachments add constraint attachments_entity_type_check
  check (entity_type in ('asset', 'asset_model', 'part_item', 'inspection', 'part_event', 'part', 'position_template'));
