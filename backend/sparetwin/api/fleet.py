"""Okuma uç noktaları. Hepsi veritabanı görünümlerinden (v_*) beslenir;
hesaplama mantığı SQL'de tek yerde durur, burada tekrar edilmez."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from .deps import TenantCtx

router = APIRouter(tags=["Filo ve parçalar"])

NOT_FOUND = "Kayıt bulunamadı"


@router.get("/sites", summary="Sahalar")
def list_sites(ctx: TenantCtx):
    with ctx.tx() as conn:
        return conn.execute(
            "select id, name, kind, city from public.sites where tenant_id = %s order by name",
            [ctx.tenant_id],
        ).fetchall()


@router.get("/assets", summary="Filo özeti (makine bazlı sağlık)")
def list_assets(ctx: TenantCtx, site_id: UUID | None = None):
    with ctx.tx() as conn:
        return conn.execute(
            """select h.*, s.name as site_name
                 from public.v_asset_health h
                 left join public.sites s on s.id = h.site_id
                where h.tenant_id = %s and (%s::uuid is null or h.site_id = %s::uuid)
                order by h.critical_parts desc, h.watch_parts desc, h.code""",
            [ctx.tenant_id, site_id, site_id],
        ).fetchall()


@router.get("/assets/{asset_id}", summary="Makine detayı ve şeması")
def get_asset(asset_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        asset = conn.execute(
            """select h.*, a.serial_no, a.year, a.meter_km, a.qr_code, a.notes, am.template_id,
                      s.name as site_name
                 from public.v_asset_health h
                 join public.assets a on a.id = h.id
                 left join public.asset_models am on am.id = a.model_id
                 left join public.sites s on s.id = a.site_id
                where h.id = %s and h.tenant_id = %s""",
            [asset_id, ctx.tenant_id],
        ).fetchone()
        if not asset:
            raise HTTPException(404, NOT_FOUND)
        # Şema: her pozisyon ve üzerindeki parça (boş pozisyon da döner)
        asset["positions"] = conn.execute(
            """select tp.code, tp.label, tp.category_code, tp.axle, tp.x, tp.y,
                      ph.id as part_item_id, ph.part_name, ph.serial_no,
                      ph.condition_pct, coalesce(ph.band, 'empty') as band,
                      ph.projected_hours_left, ph.hours_total
                 from public.template_positions tp
                 left join public.v_part_health ph
                   on ph.current_asset_id = %s and ph.current_position = tp.code
                  and ph.status = 'installed'
                where tp.template_id = %s
                order by tp.sort_order""",
            [asset_id, asset["template_id"]],
        ).fetchall()
        return asset


@router.get("/parts", summary="Parça listesi (filtreli)")
def list_parts(
    ctx: TenantCtx,
    status: Literal["in_stock", "installed", "in_repair", "refurbishing", "quarantine", "scrapped"] | None = None,
    category: str | None = None,
    asset_id: UUID | None = None,
    band: Literal["ok", "watch", "critical", "unknown"] | None = None,
    q: str | None = Query(None, max_length=60, description="Seri no veya parça adında arama"),
    limit: int = Query(100, ge=1, le=500),
):
    with ctx.tx() as conn:
        return conn.execute(
            """select ph.*, l.manufacturer, l.part_no, l.qr_code, l.cost_total
                 from public.v_part_health ph
                 join public.v_part_items_live l on l.id = ph.id
                where ph.tenant_id = %(t)s
                  and (%(status)s::text is null or ph.status::text = %(status)s)
                  and (%(cat)s::text is null or ph.category_code = %(cat)s)
                  and (%(asset)s::uuid is null or ph.current_asset_id = %(asset)s)
                  and (%(band)s::text is null or ph.band = %(band)s)
                  and (%(q)s::text is null or ph.serial_no ilike '%%' || %(q)s || '%%'
                       or ph.part_name ilike '%%' || %(q)s || '%%')
                order by ph.condition_pct nulls last
                limit %(limit)s""",
            {"t": ctx.tenant_id, "status": status, "cat": category, "asset": asset_id,
             "band": band, "q": q, "limit": limit},
        ).fetchall()


@router.get("/parts/{part_id}", summary="Parça ikizi: durum, lastik/jant bilgisi")
def get_part(part_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        part = conn.execute(
            """select l.*, ph.condition_pct, ph.band, ph.projected_hours_left
                 from public.v_part_items_live l
                 join public.v_part_health ph on ph.id = l.id
                where l.id = %s and l.tenant_id = %s""",
            [part_id, ctx.tenant_id],
        ).fetchone()
        if not part:
            raise HTTPException(404, NOT_FOUND)
        part["tire"] = conn.execute(
            """select size, construction, otd_mm, scrap_tread_mm, tread_mm, pressure_kpa,
                      tread_remaining_pct, wear_mm_per_hour, projected_hours_left,
                      cost_per_hour, expected_cost_per_hour
                 from public.v_tire_health where id = %s""",
            [part_id],
        ).fetchone()
        part["rim"] = conn.execute(
            """select ndt_interval_hours, last_ndt_hours, hours_since_ndt, compliance
                 from public.v_rim_compliance where id = %s""",
            [part_id],
        ).fetchone()
        return part


@router.get("/parts/{part_id}/events", summary="Parçanın yaşam döngüsü")
def part_events(part_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        return conn.execute(
            """select e.id, e.event_type, e.occurred_at, e.position, e.asset_hours, e.part_hours,
                      e.cost, e.reason_code, e.notes, a.code as asset_code, u.full_name as performed_by_name
                 from public.part_events e
                 left join public.assets a on a.id = e.asset_id
                 left join public.app_users u on u.id = e.performed_by
                where e.part_item_id = %s and e.tenant_id = %s
                order by e.occurred_at desc, e.id desc""",
            [part_id, ctx.tenant_id],
        ).fetchall()


@router.get("/parts/{part_id}/measurements", summary="Ölçüm geçmişi (grafik için)")
def part_measurements(part_id: UUID, ctx: TenantCtx, metric: str | None = None):
    with ctx.tx() as conn:
        return conn.execute(
            """select m.metric, m.value, m.unit, m.source, m.asset_hours, m.measured_at, m.inspection_id
                 from public.measurements m
                where m.part_item_id = %s and m.tenant_id = %s
                  and (%s::text is null or m.metric = %s)
                order by m.measured_at""",
            [part_id, ctx.tenant_id, metric, metric],
        ).fetchall()


@router.get("/rims/compliance", summary="Jant muayene (NDT) uyumluluğu")
def rim_compliance(ctx: TenantCtx):
    with ctx.tx() as conn:
        return conn.execute(
            """select * from public.v_rim_compliance where tenant_id = %s
                order by case compliance when 'overdue' then 0 when 'due_soon' then 1 else 2 end""",
            [ctx.tenant_id],
        ).fetchall()


@router.get("/catalog/categories", summary="Parça kategorileri ve ölçüm profilleri")
def categories(ctx: TenantCtx):
    with ctx.tx() as conn:
        return conn.execute(
            """select id, code, name, is_serialized, measurement_profile, required_photo_angles,
                      tenant_id is null as is_library
                 from public.part_categories
                where tenant_id is null or tenant_id = %s order by name""",
            [ctx.tenant_id],
        ).fetchall()


@router.get("/qr/{code}", summary="QR kodunu makine veya parçaya çözer")
def resolve_qr(code: str, ctx: TenantCtx):
    with ctx.tx() as conn:
        row = conn.execute(
            """select 'asset' as type, id from public.assets where qr_code = %(c)s and tenant_id = %(t)s
               union all
               select 'part' as type, id from public.part_items where qr_code = %(c)s and tenant_id = %(t)s
               limit 1""",
            {"c": code, "t": ctx.tenant_id},
        ).fetchone()
    if not row:
        raise HTTPException(404, "Bu QR kodu sistemde kayıtlı değil")
    return row
