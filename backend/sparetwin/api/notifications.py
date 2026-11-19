"""Bildirimler: liste, kişisel okundu bilgisi ve ekip bazlı durum (üstlen / gizle).

İki ayrı katman vardır:
- okundu (notification_reads): kişiseldir, yalnızca zil sayacını etkiler.
- durum (notification_states): ekip içindir. "Üstlenildi" herkesin görmesi
  gereken "biri ilgileniyor" işaretidir; "gizlendi" bu durum değişmeden
  tekrar gösterilmez. Anahtar durumu da içerdiği için kötüleşme (ör. yeni
  ölçümde daha düşük diş) kaydı kendiliğinden düşürür; sorun geçince
  anahtar listeden çıkar ve kayıt temizlenir.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..notifications import collect
from .deps import TenantCtx

router = APIRouter(prefix="/notifications", tags=["Bildirimler"])

State = Literal["acknowledged", "dismissed"]


def _decorate(conn, ctx, items: list[dict[str, Any]], include_dismissed: bool) -> dict[str, Any]:
    read = {r["key"] for r in conn.execute(
        "select key from public.notification_reads where user_id = %s and tenant_id = %s",
        [ctx.user_id, ctx.tenant_id]).fetchall()}
    states = {s["key"]: s for s in conn.execute(
        """select s.key, s.state, s.note, s.at, s.user_id, coalesce(u.full_name, u.email) as by_name
             from public.notification_states s left join public.app_users u on u.id = s.user_id
            where s.tenant_id = %s""", [ctx.tenant_id]).fetchall()}
    out = []
    for n in items:
        s = states.get(n["key"])
        n["state"] = s["state"] if s else None
        n["state_by"] = s["by_name"] if s else None
        n["state_at"] = s["at"] if s else None
        n["note"] = s["note"] if s else None
        n["read"] = n["key"] in read or n["state"] is not None  # üstlenilen/gizlenen "yeni" değildir
        if n["state"] == "dismissed" and not include_dismissed:
            continue
        out.append(n)
    return {
        "items": out,
        "unread": sum(1 for n in out if not n["read"]),
        "dismissed": sum(1 for n in items if n["state"] == "dismissed"),
    }


@router.get("", summary="Bildirimler (güncel veriden), okunmamış sayısı ve ekip durumu")
def list_notifications(ctx: TenantCtx, include_dismissed: bool = False):
    with ctx.tx() as conn:
        return _decorate(conn, ctx, collect(conn, ctx.tenant_id), include_dismissed)


class ReadIn(BaseModel):
    keys: list[str] = Field(default_factory=list, max_length=500)
    all: bool = False


@router.post("/read", summary="Okundu olarak işaretle (kişisel; belirli anahtarlar veya tümü)")
def mark_read(body: ReadIn, ctx: TenantCtx):
    with ctx.tx() as conn:
        current = [n["key"] for n in collect(conn, ctx.tenant_id)]
        keys = current if body.all else body.keys
        for k in keys:
            conn.execute(
                """insert into public.notification_reads (user_id, tenant_id, key) values (%s, %s, %s)
                   on conflict do nothing""", [ctx.user_id, ctx.tenant_id, k[:300]])
        # Artık geçerli olmayan eski okundu kayıtlarını temizle (tablo büyümesin)
        conn.execute(
            "delete from public.notification_reads where user_id = %s and tenant_id = %s and key <> all(%s)",
            [ctx.user_id, ctx.tenant_id, current])
    return {"marked": len(keys)}


class StateIn(BaseModel):
    key: str = Field(min_length=3, max_length=300)
    state: State | None = Field(None, description="acknowledged: üstlen · dismissed: gizle · null: geri al")
    note: str | None = Field(None, max_length=500)


@router.post("/state", summary="Üstlen / gizle / geri al (ekip bazlı, saha rolü ve üstü)")
def set_state(body: StateIn, ctx: TenantCtx, request: Request):
    ctx.require("technician")
    with ctx.tx() as conn:
        items = collect(conn, ctx.tenant_id)
        current = [n["key"] for n in items]
        if body.key not in current:
            raise HTTPException(404, "Bu bildirim artık geçerli değil; durum değişmiş olabilir")
        if body.state is None:
            conn.execute("delete from public.notification_states where tenant_id = %s and key = %s",
                         [ctx.tenant_id, body.key])
        else:
            conn.execute(
                """insert into public.notification_states (tenant_id, key, state, note, user_id)
                   values (%s, %s, %s, %s, %s)
                   on conflict (tenant_id, key) do update
                      set state = excluded.state, note = excluded.note, user_id = excluded.user_id, at = now()""",
                [ctx.tenant_id, body.key, body.state, body.note, ctx.user_id])
        # Sorunu geçmiş (listeden düşmüş) bildirimlerin durumları kendiliğinden kapanır
        conn.execute("delete from public.notification_states where tenant_id = %s and key <> all(%s)",
                     [ctx.tenant_id, current])
        title = next(n["title"] for n in items if n["key"] == body.key)
        request.state.audit = {"notification": title, "state": body.state, "note": body.note}
        result = _decorate(conn, ctx, items, include_dismissed=True)
    return next(n for n in result["items"] if n["key"] == body.key)
