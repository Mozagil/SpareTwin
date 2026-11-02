-- =====================================================================
-- SpareTwin — 0008: Görseller
-- ---------------------------------------------------------------------
-- Katalog kalemi, makine modeli ve tek makine için bir "görsel" (kind =
-- 'image'). Ortak kütüphanedeki kalem ve modellere de her firma kendi
-- görselini koyabilir; görsel her zaman firmaya aittir (tenant_id).
-- Saha fotoğrafları (inspeksiyon) değişmeden kind = 'photo' olarak kalır.
-- =====================================================================

alter table public.attachments drop constraint attachments_entity_type_check;
alter table public.attachments add constraint attachments_entity_type_check
  check (entity_type in ('asset', 'asset_model', 'part_item', 'inspection', 'part_event', 'part'));

-- Her kayıt için firma başına tek görsel; yenisi eskisinin yerine geçer
create unique index attachments_entity_image_uq
  on public.attachments (tenant_id, entity_type, entity_id) where kind = 'image';

-- Parçanın saha fotoğraflarını hızlı bulmak için
create index attachments_part_item_idx
  on public.attachments (part_item_id, created_at desc) where part_item_id is not null;
