"""Depo ve stok (Faz 2).

Seri numaralı parçalar (lastik, jant, silindir) stoğa "Parça teslim al" ile tek tek girer.
Sarf malzemeleri (filtre, yağ, keçe takımı) adet/litre olarak bu uç noktalarla hareket eder.
Kurallar (eksi stok yok, firma/depo kontrolü, ortalama maliyet) veritabanı fonksiyonunda.
"""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .deps import TenantCtx

router = APIRouter(prefix="/stock", tags=["Stok"])


@router.get("", summary="Stok durumu: kalem bazında toplam, depo dağılımı, değer, kritik seviye")
def stock_list(
    ctx: TenantCtx,
    category: str | None = None,
    below: bool = False,
    q: str | None = Query(None, max_length=60),
    serialized: bool | None = None,
):
    with ctx.tx() as conn:
        return conn.execute(
            """select st.*,
                      (select coalesce(sum(-sm.qty), 0) from public.stock_movements sm
                        where sm.tenant_id = st.tenant_id and sm.part_id = st.part_id and sm.kind = 'out'
                          and sm.occurred_at > now() - interval '90 days') as used_90d
                 from public.v_stock_totals st
                where st.tenant_id = %(t)s
                  and (%(c)s::text is null or st.category_code = %(c)s)
                  and (not %(b)s or st.below_min)
                  and (%(s)s::boolean is null or st.is_serialized = %(s)s)
                  and (%(q)s::text is null or st.name ilike '%%' || %(q)s || '%%' or st.part_no ilike '%%' || %(q)s || '%%')
                order by st.below_min desc, st.is_serialized, st.name""",
            {"t": ctx.tenant_id, "c": category, "b": below, "s": serialized, "q": q},
        ).fetchall()


@router.get("/{part_id}/movements", summary="Kalemin stok hareketleri")
def movements(part_id: UUID, ctx: TenantCtx, limit: int = Query(100, ge=1, le=500)):
    with ctx.tx() as conn:
        return conn.execute(
            """select sm.id, sm.kind, sm.qty, sm.unit_cost, sm.reason, sm.ref, sm.notes, sm.occurred_at,
                      s.name as site_name, a.code as asset_code, sm.asset_id, u.full_name as performed_by_name
                 from public.stock_movements sm
                 left join public.sites s on s.id = sm.site_id
                 left join public.assets a on a.id = sm.asset_id
                 left join public.app_users u on u.id = sm.performed_by
                where sm.part_id = %s and sm.tenant_id = %s
                order by sm.occurred_at desc, sm.id desc limit %s""",
            [part_id, ctx.tenant_id, limit],
        ).fetchall()


class MoveIn(BaseModel):
    part_id: UUID
    site_id: UUID | None = None
    kind: Literal["in", "out", "adjust"] = Field(description="in: giriş, out: çıkış/kullanım, adjust: sayım (qty = sayılan miktar)")
    qty: Decimal = Field(ge=0, le=1_000_000)
    unit_cost: Decimal | None = Field(None, ge=0, description="Girişte birim alış fiyatı")
    asset_id: UUID | None = Field(None, description="Çıkışta: hangi makinede kullanıldı")
    reason: str | None = Field(None, max_length=60)
    ref: str | None = Field(None, max_length=60, description="Fatura / irsaliye / iş emri no")
    notes: str | None = Field(None, max_length=1000)


class TransferIn(BaseModel):
    part_id: UUID
    from_site_id: UUID | None = None
    to_site_id: UUID | None = None
    qty: Decimal = Field(gt=0, le=1_000_000)
    notes: str | None = Field(None, max_length=1000)


def _check_part(conn, part_id: UUID, tenant_id: UUID) -> None:
    if not conn.execute(
        "select 1 from public.parts where id = %s and (tenant_id = %s or tenant_id is null)", [part_id, tenant_id]
    ).fetchone():
        raise HTTPException(404, "Katalog kalemi bulunamadı")


@router.post("/movements", status_code=201, summary="Stok hareketi: giriş, çıkış (makineye kullanım) veya sayım")
def move(body: MoveIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _check_part(conn, body.part_id, ctx.tenant_id)
        row = conn.execute(
            """select id, kind, qty, unit_cost, site_id, asset_id, occurred_at
                 from public.stock_move(%s, %s, %s, %s, %s, %s, %s, %s, %s, null, %s)""",
            [body.part_id, body.site_id, body.kind, body.qty, body.unit_cost, body.asset_id,
             body.reason, body.ref, body.notes, ctx.tenant_id],
        ).fetchone()
        row["level"] = conn.execute("select app.stock_level(%s, %s, %s) as q",
                                    [ctx.tenant_id, body.part_id, body.site_id]).fetchone()["q"]
        return row


@router.post("/transfer", status_code=201, summary="Depolar arası transfer")
def transfer(body: TransferIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _check_part(conn, body.part_id, ctx.tenant_id)
        g = conn.execute("select public.stock_transfer(%s, %s, %s, %s, %s, %s) as g",
                         [body.part_id, body.from_site_id, body.to_site_id, body.qty, body.notes, ctx.tenant_id]).fetchone()["g"]
        return {"transfer_group": g}
