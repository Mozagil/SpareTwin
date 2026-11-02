"""Katalog kalemi, makine modeli ve makine görselleri.

PUT    /catalog/parts/{id}/image          (manager)
DELETE /catalog/parts/{id}/image
PUT    /catalog/asset-models/{id}/image   (manager)
DELETE /catalog/asset-models/{id}/image
PUT    /assets/{id}/image                 (manager)
DELETE /assets/{id}/image

Okuma tarafında görseller ilgili yanıtların içinde `image` alanıyla gelir
(kısa ömürlü imzalı link). Ayrı bir istek gerekmez.
"""

import uuid
from typing import Annotated, Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, File, HTTPException, UploadFile

from ..images import ImageError, process_image
from ..storage import ALLOWED_MIME, Storage, sniff_mime
from .deps import AppSettings, AppStorage, Ctx, TenantCtx

router = APIRouter(tags=["Görseller"])

IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}

# Her tür için: kayıt firmaya mı ait, yoksa ortak kütüphanede mi olabilir?
_EXISTS = {
    "part": "select 1 from public.parts where id = %s and (tenant_id = %s or tenant_id is null)",
    "asset_model": "select 1 from public.asset_models where id = %s and (tenant_id = %s or tenant_id is null)",
    "asset": "select 1 from public.assets where id = %s and tenant_id = %s",
}
_NOT_FOUND = {"part": "Katalog kalemi bulunamadı", "asset_model": "Makine modeli bulunamadı", "asset": "Makine bulunamadı"}


# ---------- Okuma yardımcıları (diğer modüller kullanır) ----------
def image_out(storage: Storage, key: str | None, mime: str | None, att_id: Any = None, **extra) -> dict | None:
    if not key:
        return None
    return {"id": att_id, "url": storage.signed_url(key, mime or "image/jpeg", None), **extra}


def entity_image(conn: psycopg.Connection, storage: Storage, tenant_id: UUID, entity_type: str, entity_id: UUID) -> dict | None:
    row = conn.execute(
        """select id, storage_key, mime_type from public.attachments
            where tenant_id = %s and entity_type = %s and entity_id = %s and kind = 'image'""",
        [tenant_id, entity_type, entity_id],
    ).fetchone()
    return image_out(storage, row["storage_key"], row["mime_type"], row["id"]) if row else None


def part_photos(conn: psycopg.Connection, storage: Storage, tenant_id: UUID, part_item_id: UUID, limit: int = 12) -> list[dict]:
    """Parçanın sahada çekilmiş son fotoğrafları (inspeksiyonlardan)."""
    rows = conn.execute(
        """select a.id, a.storage_key, a.mime_type, a.angle, a.created_at, a.entity_id as inspection_id,
                  i.asset_hours
             from public.attachments a
             left join public.inspections i on i.id = a.entity_id and a.entity_type = 'inspection'
            where a.tenant_id = %s and a.part_item_id = %s and a.kind = 'photo'
              and a.mime_type like 'image/%%'
            order by a.created_at desc limit %s""",
        [tenant_id, part_item_id, limit],
    ).fetchall()
    return [
        image_out(storage, r["storage_key"], r["mime_type"], r["id"], angle=r["angle"],
                  created_at=r["created_at"], inspection_id=r["inspection_id"], asset_hours=r["asset_hours"])
        for r in rows
    ]


# ---------- Yazma ----------
def _read_image(file: UploadFile, max_bytes: int) -> tuple[bytes, str]:
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"Dosya en fazla {max_bytes // (1024 * 1024)} MB olabilir")
    if not data:
        raise HTTPException(422, "Dosya boş")
    mime = sniff_mime(data[:16])
    if mime not in IMAGE_MIME:
        raise HTTPException(415, "Görsel JPEG, PNG veya WEBP olmalı")
    try:
        return process_image(data, mime)
    except ImageError as e:
        raise HTTPException(422, str(e))


def _set_image(ctx: Ctx, storage: Storage, max_bytes: int, entity_type: str, entity_id: UUID, file: UploadFile):
    ctx.require("manager")
    data, mime = _read_image(file, max_bytes)
    key = f"{ctx.tenant_id}/{entity_type}/{entity_id}/{uuid.uuid4()}{ALLOWED_MIME[mime]}"
    with ctx.tx() as conn:
        if not conn.execute(_EXISTS[entity_type], [entity_id, ctx.tenant_id]).fetchone():
            raise HTTPException(404, _NOT_FOUND[entity_type])
        old = conn.execute(
            """delete from public.attachments
                where tenant_id = %s and entity_type = %s and entity_id = %s and kind = 'image'
            returning storage_key""",
            [ctx.tenant_id, entity_type, entity_id],
        ).fetchone()
        row = conn.execute(
            """insert into public.attachments
                 (tenant_id, entity_type, entity_id, kind, storage_key, file_name, mime_type, size_bytes, created_by)
               values (%s, %s, %s, 'image', %s, %s, %s, %s, %s)
               returning id, storage_key, mime_type""",
            [ctx.tenant_id, entity_type, entity_id, key, file.filename, mime, len(data), ctx.user_id],
        ).fetchone()
        storage.put(key, data, mime)  # yazma hatası olursa kayıt da geri alınır
    if old:
        storage.delete(old["storage_key"])
    return image_out(storage, row["storage_key"], row["mime_type"], row["id"])


def _delete_image(ctx: Ctx, storage: Storage, entity_type: str, entity_id: UUID) -> None:
    ctx.require("manager")
    with ctx.tx() as conn:
        old = conn.execute(
            """delete from public.attachments
                where tenant_id = %s and entity_type = %s and entity_id = %s and kind = 'image'
            returning storage_key""",
            [ctx.tenant_id, entity_type, entity_id],
        ).fetchone()
    if not old:
        raise HTTPException(404, "Görsel yok")
    storage.delete(old["storage_key"])


ImageFile = Annotated[UploadFile, File(description="JPEG, PNG veya WEBP; uzun kenar 1600 px'e küçültülür")]


@router.put("/catalog/parts/{part_id}/image", summary="Katalog kalemi görseli yükle (eskisinin yerine geçer)")
def put_part_image(part_id: UUID, file: ImageFile, ctx: TenantCtx, settings: AppSettings, storage: AppStorage):
    return _set_image(ctx, storage, settings.media_max_bytes, "part", part_id, file)


@router.delete("/catalog/parts/{part_id}/image", status_code=204, summary="Katalog kalemi görselini sil")
def delete_part_image(part_id: UUID, ctx: TenantCtx, storage: AppStorage):
    _delete_image(ctx, storage, "part", part_id)


@router.put("/catalog/asset-models/{model_id}/image", summary="Makine modeli görseli yükle")
def put_model_image(model_id: UUID, file: ImageFile, ctx: TenantCtx, settings: AppSettings, storage: AppStorage):
    return _set_image(ctx, storage, settings.media_max_bytes, "asset_model", model_id, file)


@router.delete("/catalog/asset-models/{model_id}/image", status_code=204, summary="Makine modeli görselini sil")
def delete_model_image(model_id: UUID, ctx: TenantCtx, storage: AppStorage):
    _delete_image(ctx, storage, "asset_model", model_id)


@router.put("/assets/{asset_id}/image", summary="Makinenin kendi fotoğrafını yükle (modelin görselinin önüne geçer)")
def put_asset_image(asset_id: UUID, file: ImageFile, ctx: TenantCtx, settings: AppSettings, storage: AppStorage):
    return _set_image(ctx, storage, settings.media_max_bytes, "asset", asset_id, file)


@router.delete("/assets/{asset_id}/image", status_code=204, summary="Makinenin fotoğrafını sil")
def delete_asset_image(asset_id: UUID, ctx: TenantCtx, storage: AppStorage):
    _delete_image(ctx, storage, "asset", asset_id)
