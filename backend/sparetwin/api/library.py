"""Firma kütüphanesi: parça tipleri (kategori + ölçüm profili) ve pozisyon şablonları.

Ortak kütüphane (tenant_id null) herkese açıktır ve değiştirilemez; firma kendi
tipini ve şablonunu ekler, ortak şablonu kopyalayıp düzenler. Yetki: manager ve üstü.
"""

import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, model_validator

from .deps import AppStorage, TenantCtx
from .images import entity_image

router = APIRouter(prefix="/catalog", tags=["Kütüphane"])

SLUG = r"^[a-z][a-z0-9_]{1,39}$"
POSITION_CODE = r"^[A-Z0-9][A-Z0-9_-]{0,23}$"


# ---------- Parça tipleri ----------
class MetricIn(BaseModel):
    metric: str = Field(pattern=SLUG, description="Ölçümün kalıcı anahtarı: drift_mm, voltage_v")
    label: str = Field(min_length=1, max_length=60)
    unit: str = Field("", max_length=12)
    required: bool = False
    min: float | None = Field(None, ge=-1_000_000, le=1_000_000)
    max: float | None = Field(None, ge=-1_000_000, le=1_000_000)

    @model_validator(mode="after")
    def _check(self):
        if self.min is not None and self.max is not None and self.min >= self.max:
            raise ValueError("Alt sınır üst sınırdan küçük olmalı")
        return self


def _profile(items: list[MetricIn]) -> list[dict]:
    if len({m.metric for m in items}) != len(items):
        raise HTTPException(422, "Aynı ölçüm anahtarı birden fazla kez var")
    return [m.model_dump(exclude_none=True) for m in items]


def _angles(angles: list[str]) -> list[str]:
    if len(set(angles)) != len(angles):
        raise HTTPException(422, "Aynı fotoğraf açısı birden fazla kez var")
    return angles


class CategoryIn(BaseModel):
    code: str = Field(pattern=SLUG, description="Kalıcı kod: gearbox, chain")
    name: str = Field(min_length=2, max_length=60)
    is_serialized: bool = Field(True, description="Seri numarasıyla tek tek mi, miktarla mı izlenir")
    measurement_profile: list[MetricIn] = Field(default_factory=list, max_length=12)
    required_photo_angles: list[str] = Field(default_factory=list, max_length=6)


class CategoryPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=60)
    measurement_profile: list[MetricIn] | None = Field(None, max_length=12)
    required_photo_angles: list[str] | None = Field(None, max_length=6)


CATEGORY_COLS = """id, code, name, is_serialized, measurement_profile, required_photo_angles,
                   tenant_id is null as is_library"""


def _check_angles(angles: list[str]) -> None:
    for a in angles:
        if not re.match(SLUG, a):
            raise HTTPException(422, f"Geçersiz fotoğraf açısı: {a}")


@router.post("/categories", status_code=201, summary="Parça tipi ekle (ölçüm profiliyle)")
def create_category(body: CategoryIn, ctx: TenantCtx):
    ctx.require("manager")
    profile, angles = _profile(body.measurement_profile), _angles(body.required_photo_angles)
    _check_angles(angles)
    if not body.is_serialized and (profile or angles):
        raise HTTPException(422, "Miktarla izlenen tiplerde ölçüm ve fotoğraf tanımlanmaz")
    with ctx.tx() as conn:
        # Ortak kütüphanedeki kod da alınamaz: kurallar (lastik, jant) koda bağlıdır
        if conn.execute(
            "select 1 from public.part_categories where code = %s and (tenant_id is null or tenant_id = %s)",
            [body.code, ctx.tenant_id],
        ).fetchone():
            raise HTTPException(409, f"Bu kod kullanılıyor: {body.code}")
        return conn.execute(
            f"""insert into public.part_categories
                  (tenant_id, code, name, is_serialized, measurement_profile, required_photo_angles)
                values (%s, %s, %s, %s, %s, %s) returning {CATEGORY_COLS}, 0 as part_count""",
            [ctx.tenant_id, body.code, body.name.strip(), body.is_serialized, Jsonb(profile), angles],
        ).fetchone()


def _own_category(conn, category_id: UUID, tenant_id: UUID) -> dict:
    row = conn.execute(
        "select id, code, tenant_id, is_serialized from public.part_categories where id = %s", [category_id]
    ).fetchone()
    if not row or (row["tenant_id"] is not None and row["tenant_id"] != tenant_id):
        raise HTTPException(404, "Parça tipi bulunamadı")
    if row["tenant_id"] is None:
        raise HTTPException(403, "Ortak kütüphanedeki parça tipi değiştirilemez")
    return row


@router.patch("/categories/{category_id}", summary="Parça tipini güncelle (ad, ölçüm profili, fotoğraflar)")
def update_category(category_id: UUID, body: CategoryPatch, ctx: TenantCtx):
    ctx.require("manager")
    fields: dict = {}
    if body.name is not None:
        fields["name"] = body.name.strip()
    if body.measurement_profile is not None:
        fields["measurement_profile"] = Jsonb(_profile(body.measurement_profile))
    if body.required_photo_angles is not None:
        _check_angles(body.required_photo_angles)
        fields["required_photo_angles"] = _angles(body.required_photo_angles)
    if not fields:
        raise HTTPException(422, "Güncellenecek alan yok")
    with ctx.tx() as conn:
        cat = _own_category(conn, category_id, ctx.tenant_id)
        if not cat["is_serialized"] and (body.measurement_profile or body.required_photo_angles):
            raise HTTPException(422, "Miktarla izlenen tiplerde ölçüm ve fotoğraf tanımlanmaz")
        sets = ", ".join(f"{k} = %({k})s" for k in fields)  # anahtarlar koddan, kullanıcıdan değil
        return conn.execute(
            f"""update public.part_categories set {sets} where id = %(id)s
                returning {CATEGORY_COLS},
                  (select count(*) from public.parts p where p.category_id = part_categories.id) as part_count""",
            {**fields, "id": category_id},
        ).fetchone()


@router.delete("/categories/{category_id}", status_code=204, summary="Parça tipini sil (kullanılmıyorsa)")
def delete_category(category_id: UUID, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        cat = _own_category(conn, category_id, ctx.tenant_id)
        n = conn.execute("select count(*) as n from public.parts where category_id = %s", [category_id]).fetchone()["n"]
        if n:
            raise HTTPException(409, f"Bu tipte {n} katalog kalemi var; önce onları başka tipe taşıyın ya da silin")
        used = conn.execute(
            """select pt.name from public.template_positions tp
                 join public.position_templates pt on pt.id = tp.template_id
                where pt.tenant_id = %s and tp.category_code = %s limit 1""",
            [ctx.tenant_id, cat["code"]],
        ).fetchone()
        if used:
            raise HTTPException(409, f"Bu tip “{used['name']}” şablonunda kullanılıyor")
        conn.execute("delete from public.part_categories where id = %s", [category_id])


# ---------- Pozisyon şablonları ----------
class PositionIn(BaseModel):
    code: str = Field(pattern=POSITION_CODE, description="A1-L, LIFT-CYL-L")
    label: str = Field(min_length=1, max_length=60)
    category_code: str = Field(pattern=SLUG)
    axle: int | None = Field(None, ge=1, le=12, description="Lastikler için aks no (1 = ön)")
    x: float | None = Field(None, ge=0, le=100, description="Şemada yatay konum; boşsa şemada çizilmez")
    y: float | None = Field(None, ge=0, le=100)

    @model_validator(mode="after")
    def _check(self):
        if (self.x is None) != (self.y is None):
            raise ValueError("x ve y birlikte verilir ya da birlikte boş bırakılır")
        return self


class TemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    layout: Literal["loader", "reach_stacker", "forklift", "generic"] = "generic"
    positions: list[PositionIn] = Field(min_length=1, max_length=60)


def template_out(conn, storage, template_id: UUID, tenant_id: UUID) -> dict:
    t = conn.execute(
        """select pt.id, pt.name, pt.layout, pt.tenant_id is null as is_library,
                  (select count(*) from public.asset_models am
                    where am.template_id = pt.id and am.tenant_id = %s) as model_count
             from public.position_templates pt where pt.id = %s""",
        [tenant_id, template_id],
    ).fetchone()
    t["positions"] = conn.execute(
        """select code, label, category_code, axle, x, y from public.template_positions
            where template_id = %s order by sort_order, code""",
        [template_id],
    ).fetchall()
    t["image"] = entity_image(conn, storage, tenant_id, "position_template", template_id)
    return t


def _check_positions(conn, positions: list[PositionIn], tenant_id: UUID) -> None:
    codes = [p.code for p in positions]
    if len(set(codes)) != len(codes):
        raise HTTPException(422, "Aynı pozisyon kodu birden fazla kez var")
    cats = {r["code"]: r["is_serialized"] for r in conn.execute(
        "select code, is_serialized from public.part_categories where tenant_id is null or tenant_id = %s",
        [tenant_id]).fetchall()}
    for p in positions:
        if p.category_code not in cats:
            raise HTTPException(422, f"{p.code}: parça tipi bulunamadı ({p.category_code})")
        if not cats[p.category_code]:
            raise HTTPException(422, f"{p.code}: miktarla izlenen tip ({p.category_code}) bir pozisyona takılamaz")


def _insert_positions(conn, template_id: UUID, positions: list[PositionIn]) -> None:
    for i, p in enumerate(positions, 1):
        conn.execute(
            """insert into public.template_positions (template_id, code, label, category_code, axle, x, y, sort_order)
               values (%s, %s, %s, %s, %s, %s, %s, %s)""",
            [template_id, p.code, p.label.strip(), p.category_code, p.axle, p.x, p.y, i],
        )


def _own_template(conn, template_id: UUID, tenant_id: UUID) -> None:
    row = conn.execute("select tenant_id from public.position_templates where id = %s", [template_id]).fetchone()
    if not row or (row["tenant_id"] is not None and row["tenant_id"] != tenant_id):
        raise HTTPException(404, "Pozisyon şablonu bulunamadı")
    if row["tenant_id"] is None:
        raise HTTPException(403, "Ortak kütüphane şablonu değiştirilemez; kopyasını oluşturun")


@router.post("/templates", status_code=201, summary="Pozisyon şablonu ekle")
def create_template(body: TemplateIn, ctx: TenantCtx, storage: AppStorage):
    ctx.require("manager")
    with ctx.tx() as conn:
        _check_positions(conn, body.positions, ctx.tenant_id)
        tid = conn.execute(
            "insert into public.position_templates (tenant_id, name, layout) values (%s, %s, %s) returning id",
            [ctx.tenant_id, body.name.strip(), body.layout],
        ).fetchone()["id"]
        _insert_positions(conn, tid, body.positions)
        return template_out(conn, storage, tid, ctx.tenant_id)


@router.put("/templates/{template_id}", summary="Pozisyon şablonunu güncelle (pozisyonlarıyla birlikte)")
def update_template(template_id: UUID, body: TemplateIn, ctx: TenantCtx, storage: AppStorage):
    ctx.require("manager")
    with ctx.tx() as conn:
        _own_template(conn, template_id, ctx.tenant_id)
        _check_positions(conn, body.positions, ctx.tenant_id)
        # Üzerinde parça takılı bir pozisyon silinemez, tipi değiştirilemez
        new = {p.code: p.category_code for p in body.positions}
        blocked = [
            f"{r['asset_code']} {r['position']}"
            for r in conn.execute(
                """select a.code as asset_code, pi.current_position as position, pc.code as category_code
                     from public.part_items pi
                     join public.assets a on a.id = pi.current_asset_id
                     join public.asset_models am on am.id = a.model_id
                     join public.parts p on p.id = pi.part_id
                     join public.part_categories pc on pc.id = p.category_id
                    where am.template_id = %s and pi.status = 'installed' and pi.tenant_id = %s
                    order by a.code, pi.current_position""",
                [template_id, ctx.tenant_id],
            ).fetchall()
            if new.get(r["position"]) != r["category_code"]
        ]
        if blocked:
            more = f" ve {len(blocked) - 5} pozisyon daha" if len(blocked) > 5 else ""
            raise HTTPException(
                409, f"Üzerinde parça takılı pozisyon silinemez ya da tipi değiştirilemez: {', '.join(blocked[:5])}{more}")
        conn.execute("update public.position_templates set name = %s, layout = %s where id = %s",
                     [body.name.strip(), body.layout, template_id])
        conn.execute("delete from public.template_positions where template_id = %s", [template_id])
        _insert_positions(conn, template_id, body.positions)
        return template_out(conn, storage, template_id, ctx.tenant_id)


@router.delete("/templates/{template_id}", status_code=204, summary="Pozisyon şablonunu sil (kullanılmıyorsa)")
def delete_template(template_id: UUID, ctx: TenantCtx, storage: AppStorage):
    ctx.require("manager")
    with ctx.tx() as conn:
        _own_template(conn, template_id, ctx.tenant_id)
        n = conn.execute(
            "select count(*) as n from public.asset_models where template_id = %s", [template_id]).fetchone()["n"]
        if n:
            raise HTTPException(409, f"Bu şablonu kullanan {n} makine modeli var")
        conn.execute("delete from public.position_templates where id = %s", [template_id])
        image = conn.execute(
            """delete from public.attachments where tenant_id = %s and entity_type = 'position_template'
                  and entity_id = %s returning storage_key""", [ctx.tenant_id, template_id]).fetchone()
    if image:
        storage.delete(image["storage_key"])
