"""Makine ikizini başka firmaya devretme (0024).

Devreden firma makine için tek kullanımlık bir kod üretir; alıcı firma kodu
girip makineyi, takılı parça ikizlerini ve geçmişlerini kendi filosuna alır.
Kurallar veritabanı fonksiyonlarındadır (asset_transfer_*); firmalar birbirini
göremediği için bu fonksiyonlar yetkiyi kendileri denetler.

Yetki: iki tarafta da manager ve üstü.
"""

import logging
import uuid
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..storage import ALLOWED_MIME, Storage
from .deps import AppStorage, Ctx, TenantCtx

router = APIRouter(tags=["Makine devri"])
log = logging.getLogger("sparetwin.transfers")

_OUT = """id, code, status, note, asset_id, asset_code, serial_no, model_name, part_count,
          created_at, expires_at"""


class TransferIn(BaseModel):
    note: str | None = Field(None, max_length=300, description="Kime, hangi teslimat")


class AcceptIn(BaseModel):
    code: str = Field(min_length=4, max_length=40)
    asset_code: str | None = Field(None, max_length=40, description="Alıcının filo kodu; boşsa devredenin kodu")
    site_id: UUID | None = None


@router.get("/transfers", summary="Devredilen ve devralınan makineler")
def list_transfers(ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        return conn.execute(
            """select t.id, t.asset_code, t.serial_no, t.model_name, t.part_count, t.note,
                      t.created_at, t.expires_at, t.accepted_at,
                      case when t.tenant_id = %(t)s then 'out' else 'in' end as direction,
                      case when t.status = 'pending' and t.expires_at <= now() then 'expired' else t.status end as status,
                      case when t.tenant_id = %(t)s then t.to_tenant_name else t.from_tenant_name end as counterparty,
                      -- Kod yalnızca devredene ve yalnızca kullanılabilirken görünür
                      case when t.tenant_id = %(t)s and t.status = 'pending' and t.expires_at > now() then t.code end as code,
                      case when t.tenant_id = %(t)s and t.status = 'accepted' then null else t.asset_id end as asset_id
                 from public.asset_transfers t
                where t.tenant_id = %(t)s or (t.to_tenant_id = %(t)s and t.status = 'accepted')
                order by coalesce(t.accepted_at, t.created_at) desc
                limit 200""",
            {"t": ctx.tenant_id},
        ).fetchall()


@router.post("/assets/{asset_id}/transfer", status_code=201, summary="Makine için devir kodu üret")
def create_transfer(asset_id: UUID, body: TransferIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        return conn.execute(
            f"select {_OUT} from public.asset_transfer_create(%s, %s)", [asset_id, body.note]
        ).fetchone()


@router.post("/transfers/{transfer_id}/cancel", summary="Bekleyen devri iptal et")
def cancel_transfer(transfer_id: UUID, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        return conn.execute(
            f"select {_OUT} from public.asset_transfer_cancel(%s)", [transfer_id]
        ).fetchone()


@router.get("/transfers/preview", summary="Devir kodunu sorgula: hangi makine, kimden, hangi parçalarla")
def preview_transfer(code: str, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        return conn.execute(
            "select public.asset_transfer_preview(%s, %s) as p", [code, ctx.tenant_id]
        ).fetchone()["p"]


def _copy_images(storage: Storage, ctx: Ctx, copied: list[dict]) -> None:
    """Kopyalanan model ve şablonun görseli alıcıda da görünsün: dosya çoğaltılır.

    Devir bu noktada tamamlanmıştır; görsel kopyalanamazsa devir geri alınmaz.
    """
    for c in copied:
        img = c.get("image")
        if not img or img["mime_type"] not in ALLOWED_MIME:
            continue
        key = f"{ctx.tenant_id}/{c['entity_type']}/{c['to']}/{uuid.uuid4()}{ALLOWED_MIME[img['mime_type']]}"
        try:
            storage.put(key, storage.get(img["storage_key"]), img["mime_type"])
            with ctx.tx() as conn:
                conn.execute(
                    """insert into public.attachments
                         (tenant_id, entity_type, entity_id, kind, storage_key, file_name, mime_type, size_bytes, created_by)
                       values (%s, %s, %s, 'image', %s, %s, %s, %s, %s)""",
                    [ctx.tenant_id, c["entity_type"], c["to"], key, img["file_name"], img["mime_type"],
                     img["size_bytes"], ctx.user_id],
                )
        except Exception:
            log.exception("Devirde görsel kopyalanamadı: %s %s", c["entity_type"], c["to"])


@router.post("/transfers/accept", summary="Devir kodunu kullan: makineyi ve parça ikizlerini filoya al")
def accept_transfer(body: AcceptIn, ctx: TenantCtx, storage: AppStorage):
    ctx.require("manager")
    with ctx.tx() as conn:
        result = conn.execute(
            "select public.asset_transfer_accept(%s, %s, %s, %s) as r",
            [body.code, ctx.tenant_id, body.asset_code, body.site_id],
        ).fetchone()["r"]
    _copy_images(storage, ctx, result.pop("copied"))
    return result
