"""Saha inspeksiyonu: oluştur → ölçüm gir → fotoğraf yükle → tamamla.

Tamamlama 4 kalite kapısından geçer (veritabanında `complete_inspection`).
Eksik varsa durum 'draft' kalır ve qc_flags listesi döner.
"""

import uuid
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..storage import ALLOWED_MIME, sniff_mime
from .deps import AppSettings, AppStorage, TenantCtx

router = APIRouter(prefix="/inspections", tags=["İnspeksiyon"])


class InspectionIn(BaseModel):
    asset_id: UUID
    asset_hours: Decimal | None = Field(None, ge=0)


class MeasurementIn(BaseModel):
    part_item_id: UUID
    metric: str = Field(min_length=1, max_length=40)
    value: Decimal
    unit: str | None = Field(None, max_length=10)


class MeasurementsIn(BaseModel):
    items: list[MeasurementIn] = Field(min_length=1, max_length=200)


def _get(conn, inspection_id: UUID, tenant_id: UUID) -> dict:
    row = conn.execute(
        """select i.*, a.code as asset_code from public.inspections i
             join public.assets a on a.id = i.asset_id
            where i.id = %s and i.tenant_id = %s""",
        [inspection_id, tenant_id],
    ).fetchone()
    if not row:
        raise HTTPException(404, "İnspeksiyon bulunamadı")
    return row


def _editable(row: dict) -> None:
    if row["status"] == "completed":
        raise HTTPException(409, "Tamamlanmış inspeksiyon değiştirilemez")


@router.post("", status_code=201, summary="Yeni inspeksiyon başlat")
def create(body: InspectionIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        row = conn.execute(
            """insert into public.inspections (tenant_id, asset_id, asset_hours, inspected_by)
               select a.tenant_id, a.id, %s, %s from public.assets a
                where a.id = %s and a.tenant_id = %s
               returning id, asset_id, status, asset_hours, started_at""",
            [body.asset_hours, ctx.user_id, body.asset_id, ctx.tenant_id],
        ).fetchone()
    if not row:
        raise HTTPException(404, "Makine bulunamadı")
    return row


@router.get("/{inspection_id}", summary="İnspeksiyon, ölçümleri ve fotoğrafları")
def get(inspection_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        row = _get(conn, inspection_id, ctx.tenant_id)
        row["measurements"] = conn.execute(
            """select m.id, m.part_item_id, pi.current_position as position, m.metric, m.value, m.unit
                 from public.measurements m join public.part_items pi on pi.id = m.part_item_id
                where m.inspection_id = %s order by pi.current_position, m.metric""",
            [inspection_id],
        ).fetchall()
        row["photos"] = conn.execute(
            """select id, part_item_id, angle, mime_type, size_bytes, created_at
                 from public.attachments where entity_type = 'inspection' and entity_id = %s
                order by created_at""",
            [inspection_id],
        ).fetchall()
        return row


@router.put("/{inspection_id}/measurements", summary="Ölçümleri kaydet (aynı parça+ölçüm tekrar gelirse güncellenir)")
def put_measurements(inspection_id: UUID, body: MeasurementsIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        ins = _get(conn, inspection_id, ctx.tenant_id)
        _editable(ins)
        saved = 0
        for m in body.items:
            cur = conn.execute(
                """insert into public.measurements
                     (tenant_id, part_item_id, inspection_id, metric, value, unit, asset_hours)
                   select pi.tenant_id, pi.id, %s, %s, %s, %s, %s
                     from public.part_items pi where pi.id = %s and pi.tenant_id = %s
                   on conflict (inspection_id, part_item_id, metric) where inspection_id is not null
                   do update set value = excluded.value, unit = excluded.unit, measured_at = now()""",
                [inspection_id, m.metric, m.value, m.unit, ins["asset_hours"], m.part_item_id, ctx.tenant_id],
            )
            if cur.rowcount == 0:
                raise HTTPException(404, f"Parça bulunamadı: {m.part_item_id}")
            saved += 1
        return {"saved": saved}


@router.post("/{inspection_id}/photos", status_code=201, summary="Fotoğraf yükle (parça ve açı ile)")
def upload_photo(
    inspection_id: UUID,
    ctx: TenantCtx,
    settings: AppSettings,
    storage: AppStorage,
    file: Annotated[UploadFile, File(description="JPEG, PNG, WEBP, HEIC veya PDF")],
    part_item_id: Annotated[UUID, Form()],
    angle: Annotated[str, Form(min_length=1, max_length=30, description="tread, sidewall, damage_closeup...")],
):
    ctx.require("technician")
    data = file.file.read(settings.media_max_bytes + 1)
    if len(data) > settings.media_max_bytes:
        raise HTTPException(413, f"Dosya en fazla {settings.media_max_bytes // (1024 * 1024)} MB olabilir")
    if not data:
        raise HTTPException(422, "Dosya boş")
    mime = sniff_mime(data[:16])
    if mime not in ALLOWED_MIME:
        raise HTTPException(415, "Desteklenmeyen dosya türü")

    key = f"{ctx.tenant_id}/inspection/{inspection_id}/{uuid.uuid4()}{ALLOWED_MIME[mime]}"
    with ctx.tx() as conn:
        _editable(_get(conn, inspection_id, ctx.tenant_id))
        if not conn.execute(
            "select 1 from public.part_items where id = %s and tenant_id = %s", [part_item_id, ctx.tenant_id]
        ).fetchone():
            raise HTTPException(404, "Parça bulunamadı")
        # Aynı parça + açı için önceki fotoğraf varsa yenisi onun yerine geçer
        old = conn.execute(
            """select id, storage_key from public.attachments
                where entity_type = 'inspection' and entity_id = %s and part_item_id = %s and angle = %s
                for update""",
            [inspection_id, part_item_id, angle],
        ).fetchone()
        values = [key, file.filename, mime, len(data), ctx.user_id]
        if old:
            row = conn.execute(
                """update public.attachments
                      set storage_key = %s, file_name = %s, mime_type = %s, size_bytes = %s,
                          created_by = %s, created_at = now()
                    where id = %s
                returning id, part_item_id, angle, mime_type, size_bytes, created_at""",
                [*values, old["id"]],
            ).fetchone()
        else:
            row = conn.execute(
                """insert into public.attachments
                     (tenant_id, entity_type, entity_id, part_item_id, angle, kind,
                      storage_key, file_name, mime_type, size_bytes, created_by)
                   values (%s, 'inspection', %s, %s, %s, 'photo', %s, %s, %s, %s, %s)
                   returning id, part_item_id, angle, mime_type, size_bytes, created_at""",
                [ctx.tenant_id, inspection_id, part_item_id, angle, *values],
            ).fetchone()
        # Dosya, kayıt işlemi içinde yazılır: yazma hata verirse kayıt da geri alınır.
        storage.put(key, data, mime)
    if old:
        storage.delete(old["storage_key"])
    return row


@router.post("/{inspection_id}/complete", summary="Kalite kapılarından geçirip tamamla")
def complete(inspection_id: UUID, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _get(conn, inspection_id, ctx.tenant_id)
        return conn.execute(
            "select id, status, qc_flags, completed_at from public.complete_inspection(%s)", [inspection_id]
        ).fetchone()
