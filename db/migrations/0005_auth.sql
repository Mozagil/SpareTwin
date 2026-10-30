-- =====================================================================
-- SpareTwin — 0005: Kimlik doğrulama yardımcıları
-- ---------------------------------------------------------------------
-- Giriş anında kullanıcının kimliği henüz bilinmediği için RLS altında
-- kullanıcıyı bulamayız. Bu yüzden giriş ve token işlemleri, tabloların
-- sahibi yetkisiyle çalışan (SECURITY DEFINER) dar fonksiyonlardan geçer.
-- API rolü app_users.password_hash ve refresh_tokens tablosunu doğrudan
-- okuyamaz; yalnızca bu fonksiyonları çağırabilir.
-- =====================================================================

-- Giriş: e-postaya göre kullanıcıyı ve parola özetini döndürür.
-- Parola doğrulaması API'de (argon2) yapılır.
create or replace function app.auth_find_user(p_email text)
returns table (id uuid, password_hash text, is_active boolean)
language sql stable security definer
set search_path = public
as $$
  select u.id, u.password_hash, u.is_active
    from public.app_users u
   where lower(u.email) = lower(trim(p_email));
$$;

create or replace function app.auth_touch_login(p_user uuid)
returns void language sql security definer
set search_path = public
as $$
  update public.app_users set last_login_at = now() where id = p_user;
$$;

-- Parola güncelleme (argon2 özeti API'de üretilir). Yalnızca kendi parolası.
create or replace function app.auth_set_password(p_user uuid, p_hash text)
returns void language plpgsql security definer
set search_path = public
as $$
begin
  if p_user is distinct from app.current_user_id() then
    raise exception 'Yalnızca kendi parolanızı değiştirebilirsiniz' using errcode = '42501';
  end if;
  update public.app_users set password_hash = p_hash where id = p_user;
  -- Parola değişince açık oturumlar kapanır
  update public.refresh_tokens set revoked_at = now()
   where user_id = p_user and revoked_at is null;
end $$;

create or replace function app.auth_store_refresh(
  p_user uuid, p_hash text, p_expires timestamptz, p_user_agent text default null
) returns uuid
language sql security definer
set search_path = public
as $$
  insert into public.refresh_tokens (user_id, token_hash, expires_at, user_agent)
  values (p_user, p_hash, p_expires, left(p_user_agent, 300))
  returning id;
$$;

-- Token yenileme (rotation). Geçerliyse eskiyi iptal eder, yenisini kaydeder,
-- kullanıcı kimliğini döner. İptal edilmiş bir token tekrar kullanılırsa
-- (çalınmış olabilir) o kullanıcının tüm oturumları kapatılır.
create or replace function app.auth_rotate_refresh(
  p_old_hash text, p_new_hash text, p_expires timestamptz, p_user_agent text default null
) returns uuid
language plpgsql security definer
set search_path = public
as $$
declare
  t public.refresh_tokens;
  u public.app_users;
  new_id uuid;
begin
  select * into t from public.refresh_tokens where token_hash = p_old_hash for update;
  if not found then
    return null;
  end if;

  if t.revoked_at is not null then
    update public.refresh_tokens set revoked_at = coalesce(revoked_at, now())
     where user_id = t.user_id and revoked_at is null;
    return null;
  end if;

  if t.expires_at < now() then
    return null;
  end if;

  select * into u from public.app_users where id = t.user_id;
  if not u.is_active then
    return null;
  end if;

  insert into public.refresh_tokens (user_id, token_hash, expires_at, user_agent)
  values (t.user_id, p_new_hash, p_expires, left(p_user_agent, 300))
  returning id into new_id;

  update public.refresh_tokens set revoked_at = now(), replaced_by = new_id where id = t.id;
  return t.user_id;
end $$;

create or replace function app.auth_revoke_refresh(p_hash text)
returns void language sql security definer
set search_path = public
as $$
  update public.refresh_tokens set revoked_at = now()
   where token_hash = p_hash and revoked_at is null;
$$;

-- Aktif kullanıcı kontrolü (access token geçerli olsa bile hesap kapatılmış olabilir)
create or replace function app.auth_user_active(p_user uuid)
returns boolean language sql stable security definer
set search_path = public
as $$
  select coalesce((select is_active from public.app_users where id = p_user), false);
$$;

revoke all on function app.auth_find_user(text) from public;
revoke all on function app.auth_touch_login(uuid) from public;
revoke all on function app.auth_set_password(uuid, text) from public;
revoke all on function app.auth_store_refresh(uuid, text, timestamptz, text) from public;
revoke all on function app.auth_rotate_refresh(text, text, timestamptz, text) from public;
revoke all on function app.auth_revoke_refresh(text) from public;
revoke all on function app.auth_user_active(uuid) from public;

grant execute on function app.auth_find_user(text) to sparetwin_app;
grant execute on function app.auth_touch_login(uuid) to sparetwin_app;
grant execute on function app.auth_set_password(uuid, text) to sparetwin_app;
grant execute on function app.auth_store_refresh(uuid, text, timestamptz, text) to sparetwin_app;
grant execute on function app.auth_rotate_refresh(text, text, timestamptz, text) to sparetwin_app;
grant execute on function app.auth_revoke_refresh(text) to sparetwin_app;
grant execute on function app.auth_user_active(uuid) to sparetwin_app;
