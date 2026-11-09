"""Denetim kaydı: durum değiştiren her istek kim/ne/ne zaman olarak yazılır.

Uç noktalara dokunmadan çalışır: HTTP ara katmanı yanıt üretildikten sonra
GET dışındaki istekleri `audit_logs` tablosuna ekler. Kimlik bağımlılıkları
(deps.current_user / tenant_ctx) isteğe `request.state.user_id` ve
`request.state.tenant_id` yazar; uç nokta isterse `request.state.audit`
ile özet bilgi ekler (ör. değişen eşikler).

Kayıt sahip rolüyle yazılır: uygulama rolünün tabloya insert yetkisi yok,
böylece bir API hatası ya da yetkili kullanıcı kaydı değiştiremez. Yazma
hatası isteği asla başarısız yapmaz; loglanır ve geçilir.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool

from .db import owner_tx

log = logging.getLogger("sparetwin.audit")

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
SKIP_METHODS = {"GET", "HEAD", "OPTIONS"}
# Gürültü: oturum yenileme ve kişisel okundu işareti bir "değişiklik" sayılmaz.
SKIP_PATHS = {"/auth/refresh", "/notifications/read"}
METHOD_ACTION = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}
# Varlık altındaki koleksiyonlar: /purchasing/orders → eylem "orders" değil, yöntemden (create) gelir
SUB_COLLECTIONS = {"orders", "suppliers"}


def describe(method: str, path: str) -> tuple[str | None, UUID | None, str | None]:
    """Yoldan (varlık tipi, varlık id, eylem) çıkarır.

    /parts/<id>/install → ('parts', <id>, 'install')
    /parts              → ('parts', None, 'create')
    /auth/login         → ('auth', None, 'login')
    """
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None, None, METHOD_ACTION.get(method)
    entity_type = parts[0]
    entity_id: UUID | None = None
    action: str | None = None
    rest = parts[1:]
    for i, seg in enumerate(rest):
        if UUID_RE.match(seg):
            entity_id = UUID(seg)
            tail = [s for s in rest[i + 1 :] if not UUID_RE.match(s)]
            action = tail[-1] if tail else None
            break
    if action is None:
        tail = [s for s in rest if not UUID_RE.match(s)]
        action = tail[-1] if tail else METHOD_ACTION.get(method)
    if action in SUB_COLLECTIONS:
        action = METHOD_ACTION.get(method)
    return entity_type, entity_id, action


def _write(row: dict[str, Any]) -> None:
    with owner_tx() as conn:
        tenants: list[UUID | None] = [row["tenant_id"]]
        if row["tenant_id"] is None and row["user_id"] is not None:
            # Firma bağlamı olmayan işlem (giriş, parola): kullanıcının her
            # firmasının yöneticisi görebilsin diye firma başına bir satır.
            tenants = [
                r["tenant_id"]
                for r in conn.execute(
                    "select tenant_id from public.memberships where user_id = %s", [row["user_id"]]
                ).fetchall()
            ] or [None]
        for t in tenants:
            conn.execute(
                """insert into public.audit_logs
                     (tenant_id, user_id, method, path, status, entity_type, entity_id, action, detail, ip, user_agent)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [t, row["user_id"], row["method"], row["path"], row["status"], row["entity_type"],
                 row["entity_id"], row["action"], row["detail"], row["ip"], row["user_agent"]],
            )


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def audit_middleware(request: Request, call_next):
        response = await call_next(request)
        if request.method in SKIP_METHODS or request.url.path in SKIP_PATHS:
            return response
        try:
            entity_type, entity_id, action = describe(request.method, request.url.path)
            detail = getattr(request.state, "audit", None)
            if request.url.query:
                detail = {**(detail or {}), "query": request.url.query[:500]}
            row = {
                "tenant_id": getattr(request.state, "tenant_id", None),
                "user_id": getattr(request.state, "user_id", None),
                "method": request.method,
                "path": request.url.path[:500],
                "status": response.status_code,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "detail": Jsonb(detail) if detail else None,
                "ip": (request.headers.get("x-forwarded-for") or (request.client.host if request.client else None) or "")
                      .split(",")[0].strip()[:64] or None,
                "user_agent": (request.headers.get("user-agent") or "")[:300] or None,
            }
            if row["user_id"] is None and response.status_code >= 400:
                return response  # kimliksiz ve başarısız: yetkisiz deneme gürültüsü tutulmaz
            await run_in_threadpool(_write, row)
        except Exception:  # noqa: BLE001 - denetim kaydı isteği asla düşürmez
            log.exception("Denetim kaydı yazılamadı")
        return response
