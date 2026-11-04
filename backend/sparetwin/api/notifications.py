from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..notifications import collect
from .deps import TenantCtx

router = APIRouter(prefix="/notifications", tags=["Bildirimler"])


@router.get("", summary="Bildirimler (güncel veriden) ve okunmamış sayısı")
def list_notifications(ctx: TenantCtx):
    with ctx.tx() as conn:
        items = collect(conn, ctx.tenant_id)
        read = {r["key"] for r in conn.execute(
            "select key from public.notification_reads where user_id = %s and tenant_id = %s",
            [ctx.user_id, ctx.tenant_id]).fetchall()}
    for n in items:
        n["read"] = n["key"] in read
    return {"items": items, "unread": sum(1 for n in items if not n["read"])}


class ReadIn(BaseModel):
    keys: list[str] = Field(default_factory=list, max_length=500)
    all: bool = False


@router.post("/read", summary="Okundu olarak işaretle (belirli anahtarlar veya tümü)")
def mark_read(body: ReadIn, ctx: TenantCtx):
    with ctx.tx() as conn:
        keys = [n["key"] for n in collect(conn, ctx.tenant_id)] if body.all else body.keys
        for k in keys:
            conn.execute(
                """insert into public.notification_reads (user_id, tenant_id, key) values (%s, %s, %s)
                   on conflict do nothing""", [ctx.user_id, ctx.tenant_id, k[:300]])
        # Artık geçerli olmayan eski okundu kayıtlarını temizle (tablo büyümesin)
        current = [n["key"] for n in collect(conn, ctx.tenant_id)]
        conn.execute(
            "delete from public.notification_reads where user_id = %s and tenant_id = %s and key <> all(%s)",
            [ctx.user_id, ctx.tenant_id, current])
    return {"marked": len(keys)}
