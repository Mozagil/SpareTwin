"""Kayıt işlemleri: saha, makine modeli, katalog kalemi, makine ve parça girişi.

Yetki: katalog, model, saha ve makine tanımlama → manager ve üstü.
        Parça teslim alma (depoya giriş) → technician ve üstü.
"""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from .deps import AppStorage, TenantCtx
from .images import image_out

router = APIRouter(tags=["Kayıt"])


# ---------- Sahalar ----------
class SiteIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: str | None = Field(None, max_length=40, description="maden, liman, şantiye, fabrika, depo")
    city: str | None = Field(None, max_length=80)


@router.post("/sites", status_code=201, summary="Saha ekle")
def create_site(body: SiteIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        return conn.execute(
            "insert into public.sites (tenant_id, name, kind, city) values (%s, %s, %s, %s) returning id, name, kind, city",
            [ctx.tenant_id, body.name, body.kind, body.city],
        ).fetchone()


# ---------- Pozisyon şablonları ve makine modelleri ----------
@router.get("/catalog/templates", summary="Pozisyon şablonları (pozisyonlarıyla)")
def list_templates(ctx: TenantCtx):
    with ctx.tx() as conn:
        templates = conn.execute(
            """select id, name, layout, tenant_id is null as is_library
                 from public.position_templates
                where tenant_id is null or tenant_id = %s order by name""",
            [ctx.tenant_id],
        ).fetchall()
        for t in templates:
            t["positions"] = conn.execute(
                """select code, label, category_code, axle, x, y from public.template_positions
                    where template_id = %s order by sort_order""",
                [t["id"]],
            ).fetchall()
        return templates


class AssetModelIn(BaseModel):
    manufacturer: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=2, max_length=40, description="wheel_loader, reach_stacker, forklift, press...")
    template_id: UUID


@router.get("/catalog/asset-models", summary="Makine modelleri")
def list_asset_models(ctx: TenantCtx, storage: AppStorage):
    with ctx.tx() as conn:
        rows = conn.execute(
            """select am.id, am.manufacturer, am.model, am.category, am.template_id,
                      pt.name as template_name, pt.layout, img.storage_key as img_key, img.mime_type as img_mime
                 from public.asset_models am
                 left join public.position_templates pt on pt.id = am.template_id
                 left join public.attachments img on img.tenant_id = %(t)s and img.entity_type = 'asset_model'
                       and img.entity_id = am.id and img.kind = 'image'
                where am.tenant_id is null or am.tenant_id = %(t)s
                order by am.manufacturer, am.model""",
            {"t": ctx.tenant_id},
        ).fetchall()
    for r in rows:
        r["image"] = image_out(storage, r.pop("img_key"), r.pop("img_mime"))
    return rows


@router.post("/catalog/asset-models", status_code=201, summary="Makine modeli ekle")
def create_asset_model(body: AssetModelIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        if not conn.execute(
            "select 1 from public.position_templates where id = %s and (tenant_id is null or tenant_id = %s)",
            [body.template_id, ctx.tenant_id],
        ).fetchone():
            raise HTTPException(404, "Pozisyon şablonu bulunamadı")
        return conn.execute(
            """insert into public.asset_models (tenant_id, manufacturer, model, category, template_id)
               values (%s, %s, %s, %s, %s) returning id, manufacturer, model, category, template_id""",
            [ctx.tenant_id, body.manufacturer, body.model, body.category, body.template_id],
        ).fetchone()


# ---------- Parça kataloğu ----------
class TireSpecIn(BaseModel):
    size: str = Field(min_length=3, max_length=30, description="29.5R25, 18.00-25")
    construction: Literal["radial", "bias", "solid"]
    rating: str | None = Field(None, max_length=20)
    tra_code: str | None = Field(None, max_length=10)
    otd_mm: Decimal = Field(gt=0, le=300, description="Orijinal diş derinliği")
    scrap_tread_mm: Decimal = Field(Decimal(0), ge=0, description="Söküm/kaplama sınırı")
    retreadable: bool = True

    @model_validator(mode="after")
    def _check(self):
        if self.scrap_tread_mm >= self.otd_mm:
            raise ValueError("Hurda sınırı orijinal diş derinliğinden küçük olmalı")
        return self


class RimSpecIn(BaseModel):
    size: str = Field(min_length=3, max_length=30)
    pieces: int | None = Field(None, ge=1, le=7)
    max_pressure_kpa: Decimal | None = Field(None, gt=0)
    ndt_interval_hours: Decimal | None = Field(None, gt=0, description="Tahribatsız muayene periyodu")


class CatalogPartIn(BaseModel):
    category_code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    manufacturer: str | None = Field(None, max_length=80)
    part_no: str | None = Field(None, max_length=80)
    list_cost: Decimal | None = Field(None, ge=0)
    min_stock: int = Field(0, ge=0)
    unit: Literal["adet", "litre", "kg", "metre", "takım"] = "adet"
    expected_life_hours: Decimal | None = Field(None, gt=0, description="Lastik dışı parçalarda ömür hesabı için")
    tire: TireSpecIn | None = None
    rim: RimSpecIn | None = None


@router.get("/catalog/parts", summary="Parça kataloğu (stok adediyle)")
def list_catalog_parts(ctx: TenantCtx, storage: AppStorage, category: str | None = None):
    with ctx.tx() as conn:
        rows = conn.execute(
            """select p.id, p.name, p.manufacturer, p.part_no, p.list_cost, p.min_stock, p.specs, p.unit,
                      pc.code as category_code, pc.name as category_name, pc.is_serialized,
                      ts.size as tire_size, ts.construction as tire_construction,
                      coalesce((select st.qty from public.v_stock_totals st
                        where st.part_id = p.id and st.tenant_id = %(t)s), 0) as in_stock,
                      (select count(*) from public.part_items pi
                        where pi.part_id = p.id and pi.tenant_id = %(t)s and pi.status = 'installed') as installed,
                      img.storage_key as img_key, img.mime_type as img_mime
                 from public.parts p
                 join public.part_categories pc on pc.id = p.category_id
                 left join public.tire_specs ts on ts.part_id = p.id
                 left join public.attachments img on img.tenant_id = %(t)s and img.entity_type = 'part'
                       and img.entity_id = p.id and img.kind = 'image'
                where (p.tenant_id = %(t)s or p.tenant_id is null)
                  and (%(c)s::text is null or pc.code = %(c)s)
                order by pc.name, p.name""",
            {"t": ctx.tenant_id, "c": category},
        ).fetchall()
    for r in rows:
        r["image"] = image_out(storage, r.pop("img_key"), r.pop("img_mime"))
    return rows


@router.post("/catalog/parts", status_code=201, summary="Katalog kalemi ekle (lastikse lastik bilgisi zorunlu)")
def create_catalog_part(body: CatalogPartIn, ctx: TenantCtx):
    ctx.require("manager")
    if body.category_code == "tire" and body.tire is None:
        raise HTTPException(422, "Lastik için ebat ve diş derinliği bilgisi (tire) gerekli")
    if body.category_code != "tire" and body.tire is not None:
        raise HTTPException(422, "Lastik bilgisi yalnızca lastik kategorisinde girilir")
    if body.category_code != "rim" and body.rim is not None:
        raise HTTPException(422, "Jant bilgisi yalnızca jant kategorisinde girilir")

    specs = {}
    if body.expected_life_hours is not None:
        specs["expected_life_hours"] = float(body.expected_life_hours)

    with ctx.tx() as conn:
        cat = conn.execute(
            """select id from public.part_categories
                where code = %s and (tenant_id = %s or tenant_id is null)
                order by tenant_id nulls last limit 1""",
            [body.category_code, ctx.tenant_id],
        ).fetchone()
        if not cat:
            raise HTTPException(404, f"Kategori bulunamadı: {body.category_code}")
        from psycopg.types.json import Jsonb

        part = conn.execute(
            """insert into public.parts (tenant_id, category_id, manufacturer, part_no, name, specs, list_cost, min_stock, unit)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               returning id, name, manufacturer, part_no, list_cost, min_stock, specs, unit""",
            [ctx.tenant_id, cat["id"], body.manufacturer, body.part_no, body.name, Jsonb(specs),
             body.list_cost, body.min_stock, body.unit],
        ).fetchone()
        if body.tire:
            t = body.tire
            conn.execute(
                """insert into public.tire_specs (part_id, size, construction, rating, tra_code, otd_mm, scrap_tread_mm, retreadable)
                   values (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [part["id"], t.size, t.construction, t.rating, t.tra_code, t.otd_mm, t.scrap_tread_mm, t.retreadable],
            )
        if body.rim:
            r = body.rim
            conn.execute(
                """insert into public.rim_specs (part_id, size, pieces, max_pressure_kpa, ndt_interval_hours)
                   values (%s, %s, %s, %s, %s)""",
                [part["id"], r.size, r.pieces, r.max_pressure_kpa, r.ndt_interval_hours],
            )
        part["category_code"] = body.category_code
        return part


# ---------- Makineler ----------
class AssetIn(BaseModel):
    code: str = Field(min_length=1, max_length=40, description="Filo / ekipman no: LD-07")
    model_id: UUID
    site_id: UUID | None = None
    serial_no: str | None = Field(None, max_length=80)
    year: int | None = Field(None, ge=1950, le=2100)
    meter_hours: Decimal = Field(Decimal(0), ge=0)
    meter_km: Decimal = Field(Decimal(0), ge=0)
    qr_code: str | None = Field(None, min_length=3, max_length=60, description="Boşsa otomatik üretilir")
    notes: str | None = Field(None, max_length=2000)


class AssetPatch(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=40)
    site_id: UUID | None = None
    serial_no: str | None = Field(None, max_length=80)
    year: int | None = Field(None, ge=1950, le=2100)
    status: Literal["active", "down", "maintenance", "retired"] | None = None
    notes: str | None = Field(None, max_length=2000)


def _check_site(conn, site_id: UUID | None, tenant_id: UUID) -> None:
    if site_id and not conn.execute(
        "select 1 from public.sites where id = %s and tenant_id = %s", [site_id, tenant_id]
    ).fetchone():
        raise HTTPException(404, "Saha bulunamadı")


@router.post("/assets", status_code=201, summary="Makine ekle")
def create_asset(body: AssetIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        if not conn.execute(
            "select 1 from public.asset_models where id = %s and (tenant_id is null or tenant_id = %s)",
            [body.model_id, ctx.tenant_id],
        ).fetchone():
            raise HTTPException(404, "Makine modeli bulunamadı")
        _check_site(conn, body.site_id, ctx.tenant_id)
        return conn.execute(
            """insert into public.assets
                 (tenant_id, site_id, model_id, code, serial_no, year, meter_hours, meter_km, qr_code, notes)
               values (%s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, app.new_qr('ST-A-')), %s)
               returning id, code, qr_code, meter_hours, status""",
            [ctx.tenant_id, body.site_id, body.model_id, body.code, body.serial_no, body.year,
             body.meter_hours, body.meter_km, body.qr_code, body.notes],
        ).fetchone()


@router.patch("/assets/{asset_id}", summary="Makine bilgilerini güncelle (sayaç hariç)")
def update_asset(asset_id: UUID, body: AssetPatch, ctx: TenantCtx):
    ctx.require("manager")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(422, "Güncellenecek alan yok")
    with ctx.tx() as conn:
        _check_site(conn, fields.get("site_id"), ctx.tenant_id)
        sets = ", ".join(f"{k} = %({k})s" for k in fields)  # anahtarlar modelden, kullanıcıdan değil
        row = conn.execute(
            f"""update public.assets set {sets}
                 where id = %(id)s and tenant_id = %(t)s
             returning id, code, site_id, serial_no, year, status, notes""",
            {**fields, "id": asset_id, "t": ctx.tenant_id},
        ).fetchone()
    if not row:
        raise HTTPException(404, "Makine bulunamadı")
    return row


# ---------- Parça teslim alma (depoya giriş) ----------
class ReceiveItem(BaseModel):
    serial_no: str | None = Field(None, max_length=80)
    qr_code: str | None = Field(None, min_length=3, max_length=60, description="Hazır etiket varsa; boşsa otomatik")


class ReceiveIn(BaseModel):
    part_id: UUID
    items: list[ReceiveItem] = Field(min_length=1, max_length=100)
    site_id: UUID | None = None
    purchase_cost: Decimal | None = Field(None, ge=0, description="Birim fiyat; boşsa katalog fiyatı")
    acquired_at: date | None = None
    notes: str | None = Field(None, max_length=1000)


@router.post("/parts", status_code=201, summary="Parça teslim al (bir veya birden çok adet, stoğa girer)")
def receive_parts(body: ReceiveIn, ctx: TenantCtx):
    ctx.require("technician")
    serials = [i.serial_no for i in body.items if i.serial_no]
    if len(serials) != len(set(serials)):
        raise HTTPException(422, "Aynı seri numarası listede birden fazla kez var")
    with ctx.tx() as conn:
        part = conn.execute(
            """select p.id, p.list_cost, pc.is_serialized from public.parts p
                 join public.part_categories pc on pc.id = p.category_id
                where p.id = %s and (p.tenant_id is null or p.tenant_id = %s)""",
            [body.part_id, ctx.tenant_id],
        ).fetchone()
        if not part:
            raise HTTPException(404, "Katalog kalemi bulunamadı")
        if not part["is_serialized"]:
            raise HTTPException(422, "Bu kalem adet/miktar ile izlenir; stoğa Stok sayfasından 'Giriş' ile girin")
        _check_site(conn, body.site_id, ctx.tenant_id)
        cost = body.purchase_cost if body.purchase_cost is not None else part["list_cost"]
        created = []
        for item in body.items:
            row = conn.execute(
                """insert into public.part_items
                     (tenant_id, part_id, serial_no, qr_code, status, site_id, purchase_cost, acquired_at)
                   values (%s, %s, %s, coalesce(%s, app.new_qr('ST-P-')), 'in_stock', %s, %s, coalesce(%s, current_date))
                   returning id, serial_no, qr_code, status""",
                [ctx.tenant_id, body.part_id, item.serial_no, item.qr_code, body.site_id, cost, body.acquired_at],
            ).fetchone()
            conn.execute(
                """insert into public.part_events (tenant_id, part_item_id, event_type, part_hours, notes, performed_by)
                   values (%s, %s, 'received', 0, %s, %s)""",
                [ctx.tenant_id, row["id"], body.notes, ctx.user_id],
            )
            created.append(row)
        return created
