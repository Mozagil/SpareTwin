"""Ayarlar (Faz 2): firma ayarları, firmaya özel parça kategorileri ve makine şablonları.

Ortak kütüphanedeki kategori ve şablonlar salt okunurdur; firma kendi kopyasını
oluşturup düzenler. Firma ayarlarını sahip/admin, kategori ve şablonları yönetici düzenler.
"""

import re
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

from .deps import TenantCtx

router = APIRouter(prefix="/settings", tags=["Ayarlar"])

# Modüller: ortak çekirdek (filo, kontrol, parçalar, kayıt, etiketler, ayarlar) her zaman açık.
#   tireiq : lastik ve jant yönetimi (jantlar, lastik maliyeti, jant bildirimleri)
#   parts  : yedek parça ve bakım (stok, satınalma, bakım, maliyet)
#   erp    : KOBİ ERP (Faz 4, henüz yok)
MODULES = {"tireiq": True, "parts": True, "erp": False}
DEFAULTS = {"inspection_interval_days": 30, "purchase_horizon_hours": 1000}


def get_settings(conn: psycopg.Connection, tenant_id: UUID) -> dict:
    row = conn.execute("select settings from public.tenants where id = %s", [tenant_id]).fetchone()
    s = (row or {}).get("settings") or {}
    out = {k: s.get(k, v) for k, v in DEFAULTS.items()}
    out["modules"] = {k: bool((s.get("modules") or {}).get(k, v)) for k, v in MODULES.items()}
    out["modules"]["erp"] = False  # henüz yok
    return out


class Modules(BaseModel):
    tireiq: bool = True
    parts: bool = True


class SettingsIn(BaseModel):
    inspection_interval_days: int = Field(ge=1, le=365, description="Bu kadar gün kontrol edilmeyen makine için bildirim")
    purchase_horizon_hours: int = Field(ge=100, le=10_000, description="Satınalma önerilerinde bu kadar saat içinde değişecek lastikler")
    modules: Modules = Field(default_factory=Modules)


@router.get("", summary="Firma ayarları")
def read(ctx: TenantCtx):
    with ctx.tx() as conn:
        return {**get_settings(conn, ctx.tenant_id), "can_edit": ctx.role in ("owner", "admin")}


@router.put("", summary="Firma ayarlarını kaydet (sahip/admin)")
def write(body: SettingsIn, ctx: TenantCtx):
    ctx.require("admin")
    with ctx.tx() as conn:
        conn.execute("update public.tenants set settings = settings || %s where id = %s",
                     [Jsonb(body.model_dump()), ctx.tenant_id])
        return get_settings(conn, ctx.tenant_id)


# ---------- Parça kategorileri ----------
class ProfileItem(BaseModel):
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    label: str = Field(min_length=1, max_length=60)
    unit: str | None = Field(None, max_length=12)
    required: bool = False
    min: float | None = None
    max: float | None = None


Angle = Literal["tread", "sidewall", "damage_closeup", "overview", "nameplate"]


class CategoryIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=60)
    is_serialized: bool = True
    measurement_profile: list[ProfileItem] = Field(default_factory=list, max_length=12)
    required_photo_angles: list[Angle] = Field(default_factory=list, max_length=5)

    @field_validator("code")
    @classmethod
    def code_format(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", v):
            raise ValueError("Kod küçük harf, rakam ve _ içermeli (ör. zincir, hidrolik_hortum)")
        return v


class CategoryPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=60)
    measurement_profile: list[ProfileItem] | None = None
    required_photo_angles: list[Angle] | None = None


@router.get("/categories", summary="Parça kategorileri (kütüphane + firmanın)")
def categories(ctx: TenantCtx):
    with ctx.tx() as conn:
        return conn.execute(
            """select pc.id, pc.code, pc.name, pc.is_serialized, pc.measurement_profile, pc.required_photo_angles,
                      pc.tenant_id is null as library,
                      (select count(*) from public.parts p where p.category_id = pc.id
                         and (p.tenant_id = %(t)s or p.tenant_id is null)) as catalog_items
                 from public.part_categories pc
                where pc.tenant_id is null or pc.tenant_id = %(t)s
                order by (pc.tenant_id is null) desc, pc.name""", {"t": ctx.tenant_id}).fetchall()


def _profile(items: list[ProfileItem]) -> list[dict]:
    if len({i.metric for i in items}) != len(items):
        raise HTTPException(422, "Aynı ölçüm kodu iki kez yazılmış")
    for i in items:
        if i.min is not None and i.max is not None and i.min >= i.max:
            raise HTTPException(422, f"{i.label}: en az değer en çok değerden küçük olmalı")
    return [i.model_dump(exclude_none=True) for i in items]


@router.post("/categories", status_code=201, summary="Firmaya özel parça kategorisi ekle (yönetici)")
def create_category(body: CategoryIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        if conn.execute("select 1 from public.part_categories where code = %s and (tenant_id is null or tenant_id = %s)",
                        [body.code, ctx.tenant_id]).fetchone():
            raise HTTPException(409, f"'{body.code}' kodlu bir kategori zaten var")
        return conn.execute(
            """insert into public.part_categories (tenant_id, code, name, is_serialized, measurement_profile, required_photo_angles)
               values (%s, %s, %s, %s, %s, %s) returning id, code, name""",
            [ctx.tenant_id, body.code, body.name, body.is_serialized, Jsonb(_profile(body.measurement_profile)),
             body.required_photo_angles]).fetchone()


@router.patch("/categories/{category_id}", summary="Firmanın kategorisini düzenle (kütüphane salt okunur)")
def patch_category(category_id: UUID, body: CategoryPatch, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        c = conn.execute("select tenant_id from public.part_categories where id = %s and (tenant_id is null or tenant_id = %s)",
                         [category_id, ctx.tenant_id]).fetchone()
        if not c:
            raise HTTPException(404, "Kategori bulunamadı")
        if c["tenant_id"] is None:
            raise HTTPException(403, "Ortak kütüphanedeki kategoriler değiştirilemez; kendi kategorinizi oluşturun")
        f = body.model_dump(exclude_unset=True)
        if "measurement_profile" in f:
            f["measurement_profile"] = Jsonb(_profile(body.measurement_profile or []))
        if f:
            sets = ", ".join(f"{k} = %({k})s" for k in f)
            conn.execute(f"update public.part_categories set {sets} where id = %(id)s", {**f, "id": category_id})
        return {"id": category_id}


# ---------- Makine şablonları ----------
class TemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    copy_from: UUID = Field(description="Kopyalanacak şablon (kütüphaneden veya firmanın)")


class PositionIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    label: str = Field(min_length=1, max_length=60)
    category_code: str = Field(min_length=2, max_length=40)
    axle: int | None = Field(None, ge=1, le=10)

    @field_validator("code")
    @classmethod
    def up(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{0,19}", v):
            raise ValueError("Pozisyon kodu büyük harf, rakam ve tire içermeli (ör. A3-L, BOOM-CYL)")
        return v


@router.get("/templates", summary="Makine şablonları ve pozisyonları")
def templates(ctx: TenantCtx):
    with ctx.tx() as conn:
        rows = conn.execute(
            """select pt.id, pt.name, pt.layout, pt.tenant_id is null as library,
                      (select count(*) from public.asset_models am where am.template_id = pt.id) as models
                 from public.position_templates pt where pt.tenant_id is null or pt.tenant_id = %s
                order by (pt.tenant_id is null) desc, pt.name""", [ctx.tenant_id]).fetchall()
        for r in rows:
            r["positions"] = conn.execute(
                """select code, label, category_code, axle, x is not null as on_schematic from public.template_positions
                    where template_id = %s order by sort_order, code""", [r["id"]]).fetchall()
        return rows


def _own_template(conn, template_id: UUID, tenant_id: UUID) -> dict:
    t = conn.execute("select id, tenant_id from public.position_templates where id = %s and (tenant_id is null or tenant_id = %s)",
                     [template_id, tenant_id]).fetchone()
    if not t:
        raise HTTPException(404, "Şablon bulunamadı")
    if t["tenant_id"] is None:
        raise HTTPException(403, "Ortak kütüphanedeki şablonlar değiştirilemez; kopyalayıp düzenleyin")
    return t


@router.post("/templates", status_code=201, summary="Şablonu kopyalayarak firmaya özel şablon oluştur (yönetici)")
def copy_template(body: TemplateIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        src = conn.execute("select id, layout from public.position_templates where id = %s and (tenant_id is null or tenant_id = %s)",
                           [body.copy_from, ctx.tenant_id]).fetchone()
        if not src:
            raise HTTPException(404, "Kopyalanacak şablon bulunamadı")
        new = conn.execute("insert into public.position_templates (tenant_id, name, layout) values (%s, %s, %s) returning id, name",
                           [ctx.tenant_id, body.name, src["layout"]]).fetchone()
        conn.execute(
            """insert into public.template_positions (template_id, code, label, category_code, axle, x, y, sort_order)
               select %s, code, label, category_code, axle, x, y, sort_order from public.template_positions where template_id = %s""",
            [new["id"], src["id"]])
        return new


@router.post("/templates/{template_id}/positions", status_code=201, summary="Şablona pozisyon ekle")
def add_position(template_id: UUID, body: PositionIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        _own_template(conn, template_id, ctx.tenant_id)
        if not conn.execute("select 1 from public.part_categories where code = %s and (tenant_id is null or tenant_id = %s)",
                            [body.category_code, ctx.tenant_id]).fetchone():
            raise HTTPException(422, f"'{body.category_code}' diye bir parça kategorisi yok")
        if conn.execute("select 1 from public.template_positions where template_id = %s and code = %s",
                        [template_id, body.code]).fetchone():
            raise HTTPException(409, f"{body.code} pozisyonu bu şablonda zaten var")
        order = conn.execute("select coalesce(max(sort_order), 0) + 10 as o from public.template_positions where template_id = %s",
                             [template_id]).fetchone()["o"]
        conn.execute(
            """insert into public.template_positions (template_id, code, label, category_code, axle, sort_order)
               values (%s, %s, %s, %s, %s, %s)""", [template_id, body.code, body.label, body.category_code, body.axle, order])
        return {"code": body.code}


@router.delete("/templates/{template_id}/positions/{code}", status_code=204, summary="Şablondan pozisyon sil (doluysa olmaz)")
def delete_position(template_id: UUID, code: str, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        _own_template(conn, template_id, ctx.tenant_id)
        busy = conn.execute(
            """select a.code from public.part_items pi join public.assets a on a.id = pi.current_asset_id
                 join public.asset_models am on am.id = a.model_id
                where am.template_id = %s and pi.current_position = %s and pi.status = 'installed' limit 1""",
            [template_id, code]).fetchone()
        if busy:
            raise HTTPException(409, f"{busy['code']} makinesinde {code} pozisyonunda takılı parça var; önce sökün")
        if conn.execute("delete from public.template_positions where template_id = %s and code = %s",
                        [template_id, code]).rowcount == 0:
            raise HTTPException(404, "Pozisyon bulunamadı")
