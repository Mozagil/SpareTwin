from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from ..db import user_tx
from ..security import (
    MIN_PASSWORD_LEN,
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from .deps import AppSettings, CurrentUser

router = APIRouter(prefix="/auth", tags=["Kimlik"])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LEN, max_length=200)


class Membership(BaseModel):
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    role: str


class Me(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    locale: str
    memberships: list[Membership]


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Me


def _load_me(conn, user_id: UUID) -> Me:
    u = conn.execute(
        "select id, email, full_name, locale from public.app_users where id = %s", [user_id]
    ).fetchone()
    ms = conn.execute(
        """select m.tenant_id, t.name as tenant_name, t.slug as tenant_slug, m.role::text as role
             from public.memberships m join public.tenants t on t.id = m.tenant_id
            where m.user_id = %s order by t.name""",
        [user_id],
    ).fetchall()
    return Me(**u, memberships=[Membership(**m) for m in ms])


def _issue(settings, conn, user_id: UUID, user_agent: str | None) -> TokenOut:
    access, ttl = create_access_token(settings, user_id)
    raw, digest, expires = new_refresh_token(settings)
    conn.execute("select app.auth_store_refresh(%s, %s, %s, %s)", [user_id, digest, expires, user_agent])
    return TokenOut(access_token=access, refresh_token=raw, expires_in=ttl, user=_load_me(conn, user_id))


@router.post("/login", response_model=TokenOut, summary="E-posta ve parola ile giriş")
def login(body: LoginIn, settings: AppSettings, user_agent: Annotated[str | None, Header()] = None):
    with user_tx(None) as conn:
        row = conn.execute(
            "select id, password_hash, is_active from app.auth_find_user(%s)", [body.email]
        ).fetchone()
    ok = verify_password(body.password, row["password_hash"] if row else None)
    if not row or not ok or not row["is_active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-posta veya parola hatalı")
    with user_tx(row["id"]) as conn:
        conn.execute("select app.auth_touch_login(%s)", [row["id"]])
        return _issue(settings, conn, row["id"], user_agent)


@router.post("/refresh", response_model=TokenOut, summary="Yenileme token'ı ile yeni oturum")
def refresh(body: RefreshIn, settings: AppSettings, user_agent: Annotated[str | None, Header()] = None):
    raw, digest, expires = new_refresh_token(settings)
    with user_tx(None) as conn:
        uid = conn.execute(
            "select app.auth_rotate_refresh(%s, %s, %s, %s) as uid",
            [hash_token(body.refresh_token), digest, expires, user_agent],
        ).fetchone()["uid"]
    if uid is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Oturum süresi doldu, tekrar giriş yapın")
    access, ttl = create_access_token(settings, uid)
    with user_tx(uid) as conn:
        return TokenOut(access_token=access, refresh_token=raw, expires_in=ttl, user=_load_me(conn, uid))


@router.post("/logout", status_code=204, summary="Bu cihazdaki oturumu kapat")
def logout(body: RefreshIn):
    with user_tx(None) as conn:
        conn.execute("select app.auth_revoke_refresh(%s)", [hash_token(body.refresh_token)])


@router.get("/me", response_model=Me, summary="Giriş yapan kullanıcı ve firmaları")
def me(user: CurrentUser):
    with user.tx() as conn:
        return _load_me(conn, user.user_id)


@router.post("/password", status_code=204, summary="Parola değiştir (tüm oturumlar kapanır)")
def change_password(body: PasswordIn, user: CurrentUser):
    with user.tx() as conn:
        email = conn.execute("select email from public.app_users where id = %s", [user.user_id]).fetchone()["email"]
        row = conn.execute("select password_hash from app.auth_find_user(%s)", [email]).fetchone()
        if not verify_password(body.current_password, row["password_hash"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mevcut parola hatalı")
        conn.execute("select app.auth_set_password(%s, %s)", [user.user_id, hash_password(body.new_password)])
