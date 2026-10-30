"""İstek bağlamı: kim, hangi firma adına, hangi rolle?

Her korumalı uç nokta `Ctx` alır ve veritabanına yalnızca `ctx.tx()` ile gider.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import Settings
from ..db import user_tx
from ..security import decode_access_token
from ..storage import Storage

bearer = HTTPBearer(auto_error=False, description="Giriş yanıtındaki access_token")

ROLE_ORDER = ["viewer", "technician", "manager", "admin", "owner"]


def settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def storage_dep(request: Request) -> Storage:
    return request.app.state.storage


@dataclass(frozen=True)
class UserCtx:
    user_id: UUID

    @contextmanager
    def tx(self) -> Iterator[psycopg.Connection]:
        with user_tx(self.user_id) as conn:
            yield conn


@dataclass(frozen=True)
class Ctx(UserCtx):
    tenant_id: UUID
    role: str

    def require(self, minimum: str) -> None:
        if ROLE_ORDER.index(self.role) < ROLE_ORDER.index(minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işlem için yetkiniz yok")


def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(settings_dep)],
) -> UserCtx:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Oturum geçersiz veya süresi dolmuş",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None or creds.scheme.lower() != "bearer":
        raise unauthorized
    uid = decode_access_token(settings, creds.credentials)
    if uid is None:
        raise unauthorized
    with user_tx(uid) as conn:
        active = conn.execute("select app.auth_user_active(%s) as ok", [uid]).fetchone()["ok"]
    if not active:
        raise unauthorized
    return UserCtx(uid)


def tenant_ctx(
    user: Annotated[UserCtx, Depends(current_user)],
    x_tenant_id: Annotated[UUID | None, Header(description="Çok firmalı kullanıcılar için firma")] = None,
) -> Ctx:
    with user.tx() as conn:
        rows = conn.execute(
            "select tenant_id, role::text as role from public.memberships where user_id = %s",
            [user.user_id],
        ).fetchall()
    if not rows:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hiçbir firmaya üye değilsiniz")
    if x_tenant_id is None:
        if len(rows) > 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Birden fazla firmanız var; X-Tenant-Id başlığı gerekli")
        row = rows[0]
    else:
        row = next((r for r in rows if r["tenant_id"] == x_tenant_id), None)
        if row is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu firmaya erişiminiz yok")
    return Ctx(user.user_id, row["tenant_id"], row["role"])


CurrentUser = Annotated[UserCtx, Depends(current_user)]
TenantCtx = Annotated[Ctx, Depends(tenant_ctx)]
AppSettings = Annotated[Settings, Depends(settings_dep)]
AppStorage = Annotated[Storage, Depends(storage_dep)]
