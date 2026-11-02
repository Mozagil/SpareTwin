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

from ..images import ImageError, process_image
from ..storage import ALLOWED_MIME, sniff_mime
from .deps import AppSettings, AppStorage, TenantCtx
from .images import image_out

router = APIRouter(prefix="/inspections", tags=["İnspeksiyon"])


class InspectionIn(BaseModel):
    asset_id: UUID
    asset_hours: Decimal | None = Field(None, ge=0)


class InspectionPatch(BaseModel):
    asset_hours: Decimal = Field(ge=0)


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
    if row["status"] == "rejected":
        raise HTTPException(409, "İptal edilmiş inspeksiyon değiştirilemez")


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


@router.get("", summary="İnspeksiyonlar (yarım kalanlara devam etmek için)")
def list_inspections(ctx: TenantCtx, status: str | None = "draft", asset_id: UUID | None = None, limit: int = 50):
    with ctx.tx() as conn:
        return conn.execute(
            """select i.id, i.status, i.asset_id, a.code as asset_code, i.asset_hours, i.started_at, i.completed_at,
                      u.full_name as inspected_by_name,
                      (select count(distinct m.part_item_id) from public.measurements m where m.inspection_id = i.id) as measured_parts
                 from public.inspections i
                 join public.assets a on a.id = i.asset_id
                 left join public.app_users u on u.id = i.inspected_by
                where i.tenant_id = %(t)s
                  and (%(s)s::text is null or i.status::text = %(s)s)
                  and (%(a)s::uuid is null or i.asset_id = %(a)s)
                order by i.started_at desc limit %(l)s""",
            {"t": ctx.tenant_id, "s": status or None, "a": asset_id, "l": min(max(limit, 1), 200)},
        ).fetchall()


@router.get("/{inspection_id}/sheet", summary="Kontrol kâğıdı: pozisyonlar, istenenler, önceki değerler, ilerleme")
def sheet(inspection_id: UUID, ctx: TenantCtx, storage: AppStorage):
    """Mobil form için tek istek: makinedeki her parça için ne ölçülecek, hangi
    fotoğraflar zorunlu, önceki değerler ve bu kontrolde girilenler."""
    with ctx.tx() as conn:
        ins = conn.execute(
            """select i.id, i.status, i.asset_id, i.asset_hours, i.qc_flags, i.started_at, i.completed_at,
                      a.code as asset_code, a.meter_hours, am.manufacturer, am.model, pt.layout
                 from public.inspections i
                 join public.assets a on a.id = i.asset_id
                 left join public.asset_models am on am.id = a.model_id
                 left join public.position_templates pt on pt.id = am.template_id
                where i.id = %s and i.tenant_id = %s""",
            [inspection_id, ctx.tenant_id],
        ).fetchone()
        if not ins:
            raise HTTPException(404, "İnspeksiyon bulunamadı")
        items = conn.execute(
            """select tp.code as position, tp.label, tp.category_code, tp.x, tp.y,
                      pi.id as part_item_id, pi.serial_no, p.name as part_name,
                      pc.measurement_profile as profile, pc.required_photo_angles as required_angles
                 from public.assets a
                 join public.asset_models am on am.id = a.model_id
                 join public.template_positions tp on tp.template_id = am.template_id
                 join public.part_items pi on pi.current_asset_id = a.id and pi.current_position = tp.code
                      and pi.status = 'installed'
                 join public.parts p on p.id = pi.part_id
                 join public.part_categories pc on pc.id = p.category_id
                where a.id = %s
                order by tp.sort_order""",
            [ins["asset_id"]],
        ).fetchall()
        ids = [it["part_item_id"] for it in items]
        values = conn.execute(
            """select part_item_id, metric, value from public.measurements
                where inspection_id = %s""", [inspection_id]).fetchall()
        previous = conn.execute(
            """select distinct on (m.part_item_id, m.metric) m.part_item_id, m.metric, m.value, m.measured_at
                 from public.measurements m
                 left join public.inspections i on i.id = m.inspection_id
                where m.part_item_id = any(%s) and m.inspection_id is distinct from %s
                  and (m.inspection_id is null or i.status = 'completed')
                order by m.part_item_id, m.metric, m.measured_at desc""",
            [ids, inspection_id]).fetchall()
        photos = conn.execute(
            """select id, part_item_id, angle, storage_key, mime_type from public.attachments
                where entity_type = 'inspection' and entity_id = %s and kind = 'photo'""",
            [inspection_id]).fetchall()

    done_parts = 0
    for it in items:
        pid = it["part_item_id"]
        it["values"] = {v["metric"]: v["value"] for v in values if v["part_item_id"] == pid}
        it["previous"] = {v["metric"]: {"value": v["value"], "at": v["measured_at"]} for v in previous if v["part_item_id"] == pid}
        it["photos"] = [image_out(storage, ph["storage_key"], ph["mime_type"], ph["id"], angle=ph["angle"])
                        for ph in photos if ph["part_item_id"] == pid]
        have_angles = {ph["angle"] for ph in it["photos"]}
        missing = [{"kind": "metric", "key": m["metric"], "label": m["label"]}
                   for m in it["profile"] if m.get("required") and m["metric"] not in it["values"]]
        missing += [{"kind": "photo", "key": a} for a in it["required_angles"] if a not in have_angles]
        it["missing"] = missing
        it["required"] = bool(it["required_angles"]) or any(m.get("required") for m in it["profile"])
        it["started"] = bool(it["values"] or it["photos"])
        it["complete"] = it["started"] and not missing
        done_parts += 1 if (it["required"] and it["complete"]) else 0
    ins["items"] = items
    ins["progress"] = {"done": done_parts, "total": sum(1 for it in items if it["required"])}
    return ins


@router.patch("/{inspection_id}", summary="Motor saatini düzelt (yalnızca taslak)")
def patch(inspection_id: UUID, body: InspectionPatch, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _editable(_get(conn, inspection_id, ctx.tenant_id))
        conn.execute("update public.inspections set asset_hours = %s where id = %s", [body.asset_hours, inspection_id])
        # Bu kontrolde girilen ölçümlerin motor saati de güncellenir
        conn.execute("update public.measurements set asset_hours = %s where inspection_id = %s",
                     [body.asset_hours, inspection_id])
        return conn.execute("select id, status, asset_hours from public.inspections where id = %s", [inspection_id]).fetchone()


@router.post("/{inspection_id}/cancel", summary="Taslak kontrolü iptal et")
def cancel(inspection_id: UUID, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _editable(_get(conn, inspection_id, ctx.tenant_id))
        return conn.execute(
            "update public.inspections set status = 'rejected' where id = %s returning id, status", [inspection_id]
        ).fetchone()


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
    try:
        data, mime = process_image(data, mime)  # yön düzeltme, küçültme, GPS/meta veri silme
    except ImageError as e:
        raise HTTPException(422, str(e))

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
        if _get(conn, inspection_id, ctx.tenant_id)["status"] == "rejected":
            raise HTTPException(409, "İptal edilmiş inspeksiyon tamamlanamaz")
        return conn.execute(
            "select id, status, qc_flags, completed_at from public.complete_inspection(%s)", [inspection_id]
        ).fetchone()
