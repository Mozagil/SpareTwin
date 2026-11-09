"""SpareTwin API.

Çalıştırma:  make api   (veya: python -m uvicorn sparetwin.main:create_app --factory --reload)
Dokümantasyon: /docs (Swagger), /redoc
"""

import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from . import __version__, audit
from .api import (
    auth, fleet, images, imports, inspections, labels, lifecycle, media, notifications, organization, registry, stock,
)
from .config import Settings, get_settings
from .db import close_pool, http_status_for, init_pool, owner_tx, user_message_for
from .migrate import run as run_migrations
from .storage import build_storage

log = logging.getLogger("sparetwin")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.migrate_on_start:
            applied = run_migrations(settings.database_url, settings.migrations_dir)
            if applied:
                log.info("Uygulanan migrasyonlar: %s", ", ".join(applied))
        init_pool(settings.database_url, settings.db_pool_min, settings.db_pool_max)
        app.state.storage = build_storage(settings)
        yield
        close_pool()

    app = FastAPI(
        title="SpareTwin API",
        version=__version__,
        description="Dijital parça ikizi platformu. Kimlik: `POST /auth/login` → `Authorization: Bearer <access_token>`.",
        lifespan=lifespan,
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url="/redoc" if settings.env != "prod" else None,
    )

    app.state.settings = settings

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=False,  # token başlıkta taşınır, çerez kullanılmaz
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Tenant-Id"],
            max_age=600,
        )

    @app.exception_handler(psycopg.Error)
    async def db_error(request: Request, exc: psycopg.Error):
        code = http_status_for(exc)
        if code is None:
            log.exception("Beklenmeyen veritabanı hatası", exc_info=exc)
            return JSONResponse({"detail": "Beklenmeyen bir hata oluştu"}, status_code=500)
        return JSONResponse({"detail": user_message_for(exc)}, status_code=code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()
        ]
        return JSONResponse({"detail": "Girilen bilgiler geçersiz", "fields": fields}, status_code=422)

    @app.get("/", include_in_schema=False)
    def root():
        # Codespaces port kontrolleri ve tarayıcıyla açanlar 404 yerine dokümana gitsin
        if settings.env != "prod":
            return RedirectResponse("/docs")
        return {"status": "ok"}

    @app.get("/health", tags=["Sistem"], summary="Sağlık kontrolü")
    def health():
        with owner_tx() as conn:
            conn.execute("select 1")
        return {"status": "ok", "version": __version__, "mode": settings.deployment_mode}

    for r in (auth.router, fleet.router, registry.router, images.router, lifecycle.router, inspections.router,
              media.router, labels.router, imports.router, notifications.router, stock.router, organization.router):
        app.include_router(r)
    audit.install(app)  # durum değiştiren her isteği denetim kaydına yazar
    return app

