"""Firma ayarları (eşikler) ve denetim kaydı. Yalnızca yöneticiler değiştirir/okur."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, model_validator

from ..tenant_settings import DEFAULT_THRESHOLDS, THRESHOLD_LIMITS, thresholds
from .deps import TenantCtx

router = APIRouter(tags=["Firma"])


class Thresholds(BaseModel):
    critical_pct: float = Field(DEFAULT_THRESHOLDS["critical_pct"], description="Kalan ömür/diş bu yüzdenin altında: kritik")
    watch_pct: float = Field(DEFAULT_THRESHOLDS["watch_pct"], description="Bu yüzdenin altında: izlemede")
    rim_due_soon_pct: float = Field(DEFAULT_THRESHOLDS["rim_due_soon_pct"], description="NDT periyodunun bu yüzdesi dolunca 'yaklaşıyor'")
    inspection_interval_days: float = Field(DEFAULT_THRESHOLDS["inspection_interval_days"], description="Bu kadar gün kontrol edilmeyen makine bildirilir")
    need_horizon_hours: float = Field(DEFAULT_THRESHOLDS["need_horizon_hours"], description="Bu kadar saat içinde ömrü biten takılı parça sipariş ihtiyacına girer")
    maint_warn_hours: float = Field(DEFAULT_THRESHOLDS["maint_warn_hours"], description="Sıradaki bakıma bu kadar saat kala 'yaklaşıyor'")
    maint_warn_days: float = Field(DEFAULT_THRESHOLDS["maint_warn_days"], description="Takvim bazlı bakıma bu kadar gün kala 'yaklaşıyor'")
    downtime_cost_per_hour: float = Field(DEFAULT_THRESHOLDS["downtime_cost_per_hour"], description="Arızalı makinenin saat başı kaybı; TCO raporunda duruş maliyeti")

    @model_validator(mode="after")
    def _ranges(self):
        for k, (lo, hi) in THRESHOLD_LIMITS.items():
            v = getattr(self, k)
            if not (lo <= v <= hi):
                raise ValueError(f"{k} {lo:g} ile {hi:g} arasında olmalı")
        if self.critical_pct >= self.watch_pct:
            raise ValueError("Kritik eşik, izleme eşiğinden küçük olmalı")
        return self


class OrganizationOut(BaseModel):
    id: UUID
    name: str
    slug: str
    plan: str
    currency: str
    thresholds: Thresholds
    defaults: Thresholds = Thresholds()


class OrganizationPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    thresholds: Thresholds | None = None


def _load(conn, tenant_id: UUID) -> OrganizationOut:
    t = conn.execute("select id, name, slug, plan, settings from public.tenants where id = %s", [tenant_id]).fetchone()
    if t is None:
        raise HTTPException(404, "Firma bulunamadı")
    return OrganizationOut(
        id=t["id"], name=t["name"], slug=t["slug"], plan=t["plan"],
        currency=(t["settings"] or {}).get("currency", "USD"),
        thresholds=Thresholds(**thresholds(conn, tenant_id)),
    )


@router.get("/organization", response_model=OrganizationOut, summary="Firma bilgisi ve uyarı eşikleri")
def get_organization(ctx: TenantCtx):
    with ctx.tx() as conn:
        return _load(conn, ctx.tenant_id)


@router.patch("/organization", response_model=OrganizationOut, summary="Firma adı ve eşikleri güncelle (yönetici)")
def patch_organization(body: OrganizationPatch, ctx: TenantCtx, request: Request):
    ctx.require("admin")
    with ctx.tx() as conn:
        before = _load(conn, ctx.tenant_id)
        changes: dict[str, Any] = {}
        if body.name is not None and body.name.strip() != before.name:
            conn.execute("update public.tenants set name = %s where id = %s", [body.name.strip(), ctx.tenant_id])
            changes["name"] = {"from": before.name, "to": body.name.strip()}
        if body.thresholds is not None:
            new = body.thresholds.model_dump()
            diff = {k: {"from": getattr(before.thresholds, k), "to": v} for k, v in new.items()
                    if getattr(before.thresholds, k) != v}
            if diff:
                conn.execute(
                    "update public.tenants set settings = settings || jsonb_build_object('thresholds', %s::jsonb) where id = %s",
                    [Jsonb(new), ctx.tenant_id],
                )
                changes["thresholds"] = diff
        if changes:
            request.state.audit = changes  # denetim kaydına ne değiştiği yazılsın
        return _load(conn, ctx.tenant_id)


class AuditRow(BaseModel):
    id: int
    at: datetime
    user_id: UUID | None
    user_email: str | None
    user_name: str | None
    method: str
    path: str
    status: int
    entity_type: str | None
    entity_id: UUID | None
    action: str | None
    detail: dict[str, Any] | None
    ip: str | None


@router.get("/audit", response_model=list[AuditRow], summary="Denetim kaydı: kim, ne, ne zaman (yönetici)")
def list_audit(
    ctx: TenantCtx,
    limit: int = Query(100, ge=1, le=500),
    before: datetime | None = Query(None, description="Bu andan önceki kayıtlar (sayfalama)"),
    user_id: UUID | None = None,
    entity_id: UUID | None = None,
    q: str | None = Query(None, max_length=100, description="Yol veya eylemde geçen metin"),
):
    ctx.require("admin")
    with ctx.tx() as conn:
        return conn.execute(
            """select l.id, l.at, l.user_id, u.email as user_email, u.full_name as user_name,
                      l.method, l.path, l.status, l.entity_type, l.entity_id, l.action, l.detail, l.ip
                 from public.audit_logs l
                 left join public.app_users u on u.id = l.user_id
                where l.tenant_id = %(tenant)s
                  and (%(before)s::timestamptz is null or l.at < %(before)s::timestamptz)
                  and (%(user)s::uuid is null or l.user_id = %(user)s::uuid)
                  and (%(entity)s::uuid is null or l.entity_id = %(entity)s::uuid)
                  and (%(q)s::text is null or l.path ilike '%%' || %(q)s || '%%' or l.action ilike '%%' || %(q)s || '%%')
                order by l.at desc, l.id desc
                limit %(limit)s""",
            {"tenant": ctx.tenant_id, "before": before, "user": user_id, "entity": entity_id, "q": q, "limit": limit},
        ).fetchall()
