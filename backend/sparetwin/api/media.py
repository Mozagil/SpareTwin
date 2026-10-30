"""Dosya erişimi.

1) İstemci GET /media/{id}/url ile (oturumla) kısa ömürlü bir link ister.
2) Link doğrudan <img src> içinde kullanılabilir; oturum başlığı gerekmez.
   Yerel depoda link bu API'nin /media/file/{token} adresidir, S3'te
   S3'ün imzalı adresidir. Link birkaç dakika sonra geçersiz olur.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..security import decode_media_token
from ..storage import LocalStorage
from .deps import AppSettings, AppStorage, TenantCtx

router = APIRouter(prefix="/media", tags=["Dosyalar"])


@router.get("/{attachment_id}/url", summary="Dosya için kısa ömürlü link")
def media_url(attachment_id: UUID, ctx: TenantCtx, settings: AppSettings, storage: AppStorage):
    with ctx.tx() as conn:
        row = conn.execute(
            "select storage_key, mime_type, file_name from public.attachments where id = %s and tenant_id = %s",
            [attachment_id, ctx.tenant_id],
        ).fetchone()
    if not row:
        raise HTTPException(404, "Dosya bulunamadı")
    return {
        "url": storage.signed_url(row["storage_key"], row["mime_type"], row["file_name"]),
        "expires_in": settings.media_url_minutes * 60,
    }


@router.get("/file/{token}", include_in_schema=False)
def media_file(token: str, settings: AppSettings, storage: AppStorage):
    if not isinstance(storage, LocalStorage):
        raise HTTPException(404, "Bulunamadı")
    payload = decode_media_token(settings, token)
    if not payload:
        raise HTTPException(403, "Linkin süresi dolmuş")
    path = storage.path_for(payload["k"])
    if not path.exists():
        raise HTTPException(404, "Dosya bulunamadı")
    return FileResponse(
        path,
        media_type=payload["m"],
        filename=payload.get("n") or path.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
