-- =====================================================================
-- SpareTwin — Satır bazlı güvenlik (RLS)
-- ---------------------------------------------------------------------
-- Kural: Bir kullanıcı yalnızca üyesi olduğu firmanın (tenant) verisini
-- görür. API'de bir filtre unutulsa bile veri sızmaz; güvenliğin son
-- halkası veritabanıdır.
-- =====================================================================

grant usage on schema public, app to sparetwin_app;
grant execute on function app.current_user_id() to sparetwin_app;

create or replace function app.is_member(p_tenant uuid)
returns boolean
language sql stable security definer
set search_path = public
as $$
  select exists (
    select 1 from public.memberships m
    where m.tenant_id = p_tenant and m.user_id = app.current_user_id()
  );
$$;

create or replace function app.has_role(p_tenant uuid, p_roles app.member_role[])
returns boolean
language sql stable security definer
set search_path = public
as $$
  select exists (
    select 1 from public.memberships m
    where m.tenant_id = p_tenant and m.user_id = app.current_user_id() and m.role = any (p_roles)
  );
$$;

grant execute on function app.is_member(uuid) to sparetwin_app;
grant execute on function app.has_role(uuid, app.member_role[]) to sparetwin_app;

-- ---------- Firma, profil, üyelik ------------------------------------
alter table public.tenants enable row level security;
create policy tenants_select on public.tenants for select to sparetwin_app
  using (app.is_member(id));
create policy tenants_update on public.tenants for update to sparetwin_app
  using (app.has_role(id, '{owner,admin}'));

-- Kullanıcılar: kendini ve aynı firmadaki kişileri görür; parola özeti hiç görünmez.
alter table public.app_users enable row level security;
grant select (id, email, full_name, locale, is_active, last_login_at, created_at) on public.app_users to sparetwin_app;
grant update (full_name, locale) on public.app_users to sparetwin_app;
create policy app_users_select on public.app_users for select to sparetwin_app
  using (
    id = app.current_user_id()
    or exists (
      select 1 from public.memberships mine
      join public.memberships theirs on theirs.tenant_id = mine.tenant_id
      where mine.user_id = app.current_user_id() and theirs.user_id = app_users.id
    )
  );
create policy app_users_update on public.app_users for update to sparetwin_app
  using (id = app.current_user_id());

-- Token tablosuna API rolü doğrudan erişemez; yalnızca 0005'teki fonksiyonlar.
alter table public.refresh_tokens enable row level security;

alter table public.memberships enable row level security;
create policy memberships_select on public.memberships for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy memberships_write on public.memberships for all to sparetwin_app
  using (app.has_role(tenant_id, '{owner,admin}'))
  with check (app.has_role(tenant_id, '{owner,admin}'));

grant select, update on public.tenants to sparetwin_app;
grant select, insert, update, delete on public.memberships to sparetwin_app;

-- ---------- Firma verisi tabloları (standart politika seti) ----------
-- okuma: tüm üyeler | ekleme/güncelleme: saha dahil operasyonel roller
-- silme: yöneticiler
do $$
declare
  t text;
begin
  foreach t in array array[
    'sites', 'assets', 'meter_readings', 'part_items',
    'inspections', 'measurements', 'attachments'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('grant select, insert, update, delete on public.%I to sparetwin_app', t);
    execute format(
      'create policy %1$s_select on public.%1$I for select to sparetwin_app using (app.is_member(tenant_id))', t);
    execute format(
      'create policy %1$s_insert on public.%1$I for insert to sparetwin_app
         with check (app.has_role(tenant_id, ''{owner,admin,manager,technician}''))', t);
    execute format(
      'create policy %1$s_update on public.%1$I for update to sparetwin_app
         using (app.has_role(tenant_id, ''{owner,admin,manager,technician}''))', t);
    execute format(
      'create policy %1$s_delete on public.%1$I for delete to sparetwin_app
         using (app.has_role(tenant_id, ''{owner,admin,manager}''))', t);
  end loop;
end $$;

-- Yaşam döngüsü defteri append-only: güncelleme ve silme politikası yok.
alter table public.part_events enable row level security;
grant select, insert on public.part_events to sparetwin_app;
create policy part_events_select on public.part_events for select to sparetwin_app
  using (app.is_member(tenant_id));
create policy part_events_insert on public.part_events for insert to sparetwin_app
  with check (app.has_role(tenant_id, '{owner,admin,manager,technician}'));

-- ---------- Kütüphane tabloları (ortak + firmaya özel) ---------------
-- tenant_id null olan satırlar platformun ortak kütüphanesidir: herkes okur,
-- kimse (servis rolü hariç) değiştiremez.
do $$
declare
  t text;
begin
  foreach t in array array['position_templates', 'asset_models', 'part_categories', 'parts'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('grant select, insert, update, delete on public.%I to sparetwin_app', t);
    execute format(
      'create policy %1$s_select on public.%1$I for select to sparetwin_app
         using (tenant_id is null or app.is_member(tenant_id))', t);
    execute format(
      'create policy %1$s_write on public.%1$I for all to sparetwin_app
         using (tenant_id is not null and app.has_role(tenant_id, ''{owner,admin,manager}''))
         with check (tenant_id is not null and app.has_role(tenant_id, ''{owner,admin,manager}''))', t);
  end loop;
end $$;

alter table public.template_positions enable row level security;
grant select, insert, update, delete on public.template_positions to sparetwin_app;
create policy template_positions_select on public.template_positions for select to sparetwin_app
  using (exists (
    select 1 from public.position_templates pt
    where pt.id = template_id and (pt.tenant_id is null or app.is_member(pt.tenant_id))
  ));
create policy template_positions_write on public.template_positions for all to sparetwin_app
  using (exists (
    select 1 from public.position_templates pt
    where pt.id = template_id and pt.tenant_id is not null
      and app.has_role(pt.tenant_id, '{owner,admin,manager}')
  ))
  with check (exists (
    select 1 from public.position_templates pt
    where pt.id = template_id and pt.tenant_id is not null
      and app.has_role(pt.tenant_id, '{owner,admin,manager}')
  ));

-- Kimlik sütunları için sıra (identity) izinleri
grant usage on all sequences in schema public to sparetwin_app;
