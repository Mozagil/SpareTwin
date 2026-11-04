-- =====================================================================
-- SpareTwin — 0011: Bildirimlerin okundu bilgisi
-- ---------------------------------------------------------------------
-- Bildirimler saklanmaz, her istekte güncel veriden üretilir (kritik
-- parça, jant muayenesi, stok, uzun süredir kontrol edilmeyen makine).
-- Her bildirimin durumunu da içeren bir anahtarı vardır; ör.
--   part:<id>:critical:<son ölçüm tarihi>
-- Durum değişince anahtar değişir ve bildirim yeniden "okunmamış" olur.
-- Burada yalnızca kullanıcının hangi anahtarları okuduğu tutulur.
-- E-posta bildirimleri (sunucu aşaması) aynı listeyi kullanacak.
-- =====================================================================

create table public.notification_reads (
  user_id    uuid not null references public.app_users(id) on delete cascade,
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  key        text not null,
  read_at    timestamptz not null default now(),
  primary key (user_id, tenant_id, key)
);

alter table public.notification_reads enable row level security;
grant select, insert, delete on public.notification_reads to sparetwin_app;
create policy notification_reads_own on public.notification_reads for all to sparetwin_app
  using (user_id = app.current_user_id() and app.is_member(tenant_id))
  with check (user_id = app.current_user_id() and app.is_member(tenant_id));
