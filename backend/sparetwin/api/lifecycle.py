"""Durum değiştiren işlemler. Kuralların tamamı veritabanı fonksiyonlarında;
burada yalnızca giriş doğrulama ve firma kontrolü var."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .deps import TenantCtx

router = APIRouter(tags=["Yaşam döngüsü"])

NextStatus = Literal["in_stock", "in_repair", "refurbishing", "quarantine", "scrapped"]
EventType = Literal["received", "inspected", "repaired", "refurbished", "rotated", "transferred", "scrapped", "note"]


class MeterIn(BaseModel):
    hours: Decimal | None = Field(None, ge=0, le=1_000_000)
    km: Decimal | None = Field(None, ge=0, le=10_000_000)


class InstallIn(BaseModel):
    asset_id: UUID
    position: str = Field(min_length=1, max_length=40)
    hours: Decimal | None = Field(None, ge=0, description="Boşsa makinenin güncel saati")
    notes: str | None = Field(None, max_length=1000)


class RemoveIn(BaseModel):
    reason: str = Field(min_length=1, max_length=40, description="worn_out, cut, impact, leak, rotation...")
    next_status: NextStatus = "in_stock"
    hours: Decimal | None = Field(None, ge=0)
    cost: Decimal | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=1000)


class EventIn(BaseModel):
    event: EventType
    reason: str | None = Field(None, max_length=40, description="NDT muayenesi için 'ndt'")
    cost: Decimal | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=1000)
    next_status: NextStatus | None = None


def _own_part(conn, part_id: UUID, tenant_id: UUID) -> None:
    if not conn.execute(
        "select 1 from public.part_items where id = %s and tenant_id = %s", [part_id, tenant_id]
    ).fetchone():
        raise HTTPException(404, "Parça bulunamadı")


def _own_asset(conn, asset_id: UUID, tenant_id: UUID) -> None:
    if not conn.execute(
        "select 1 from public.assets where id = %s and tenant_id = %s", [asset_id, tenant_id]
    ).fetchone():
        raise HTTPException(404, "Makine bulunamadı")


@router.post("/assets/{asset_id}/meter", summary="Motor saati / km gir")
def record_meter(asset_id: UUID, body: MeterIn, ctx: TenantCtx):
    ctx.require("technician")
    if body.hours is None and body.km is None:
        raise HTTPException(422, "Saat veya km girilmeli")
    with ctx.tx() as conn:
        _own_asset(conn, asset_id, ctx.tenant_id)
        return conn.execute(
            "select id, code, meter_hours, meter_km from public.record_meter_reading(%s, %s, %s)",
            [asset_id, body.hours, body.km],
        ).fetchone()


@router.post("/parts/{part_id}/install", summary="Parçayı makineye tak")
def install(part_id: UUID, body: InstallIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _own_part(conn, part_id, ctx.tenant_id)
        _own_asset(conn, body.asset_id, ctx.tenant_id)
        return conn.execute(
            """select id, status, current_asset_id, current_position, installed_at_hours
                 from public.install_part_item(%s, %s, %s, %s, %s)""",
            [part_id, body.asset_id, body.position, body.hours, body.notes],
        ).fetchone()


@router.post("/parts/{part_id}/remove", summary="Parçayı sök")
def remove(part_id: UUID, body: RemoveIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _own_part(conn, part_id, ctx.tenant_id)
        return conn.execute(
            """select id, status, hours_accumulated
                 from public.remove_part_item(%s, %s, %s::app.part_item_status, %s, %s, %s)""",
            [part_id, body.reason, body.next_status, body.hours, body.cost, body.notes],
        ).fetchone()


@router.post("/parts/{part_id}/events", summary="Olay kaydet (tamir, NDT, kaplama dönüşü...)")
def add_event(part_id: UUID, body: EventIn, ctx: TenantCtx):
    ctx.require("technician")
    with ctx.tx() as conn:
        _own_part(conn, part_id, ctx.tenant_id)
        return conn.execute(
            """select id, event_type, part_hours, occurred_at
                 from public.log_part_event(%s, %s::app.part_event_type, %s, %s, %s, %s::app.part_item_status)""",
            [part_id, body.event, body.reason, body.cost, body.notes, body.next_status],
        ).fetchone()
