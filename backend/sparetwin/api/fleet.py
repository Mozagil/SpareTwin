"""Okuma uç noktaları. Hepsi veritabanı görünümlerinden (v_*) beslenir;
hesaplama mantığı SQL'de tek yerde durur, burada tekrar edilmez."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .deps import AppStorage, TenantCtx
from .images import entity_image, image_out, part_photos

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
def list_assets(ctx: TenantCtx, storage: AppStorage, site_id: UUID | None = None):
    with ctx.tx() as conn:
        rows = conn.execute(
            """select h.*, s.name as site_name,
                      coalesce(ai.storage_key, mi.storage_key) as img_key,
                      coalesce(ai.mime_type, mi.mime_type) as img_mime
                 from public.v_asset_health h
                 join public.assets a on a.id = h.id
                 left join public.sites s on s.id = h.site_id
                 left join public.attachments ai on ai.tenant_id = h.tenant_id and ai.entity_type = 'asset'
                       and ai.entity_id = h.id and ai.kind = 'image'
                 left join public.attachments mi on mi.tenant_id = h.tenant_id and mi.entity_type = 'asset_model'
                       and mi.entity_id = a.model_id and mi.kind = 'image'
                where h.tenant_id = %s and (%s::uuid is null or h.site_id = %s::uuid)
                order by h.critical_parts desc, h.watch_parts desc, h.code""",
            [ctx.tenant_id, site_id, site_id],
        ).fetchall()
    for r in rows:
        r["image"] = image_out(storage, r.pop("img_key"), r.pop("img_mime"))
    return rows


@router.get("/assets/{asset_id}", summary="Makine detayı ve şeması")
def get_asset(asset_id: UUID, ctx: TenantCtx, storage: AppStorage):
    with ctx.tx() as conn:
        asset = conn.execute(
            """select h.*, a.serial_no, a.year, a.meter_km, a.qr_code, a.notes, am.template_id, a.model_id,
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
        own = entity_image(conn, storage, ctx.tenant_id, "asset", asset_id)
        model_img = entity_image(conn, storage, ctx.tenant_id, "asset_model", asset["model_id"]) if asset["model_id"] else None
        asset["image"] = ({**own, "source": "asset"} if own
                          else {**model_img, "source": "model"} if model_img else None)
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
def get_part(part_id: UUID, ctx: TenantCtx, storage: AppStorage):
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
        part["image"] = entity_image(conn, storage, ctx.tenant_id, "part", part["part_id"])
        part["photos"] = part_photos(conn, storage, ctx.tenant_id, part_id)
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


@router.get("/parts/{part_id}/wear", summary="Lastik aşınma eğrisi: parça saatine göre diş derinliği ve tahmin")
def part_wear(part_id: UUID, ctx: TenantCtx):
    """Grafik için hazır veri. Ölçümler makine saatiyle kaydedilir; burada lastiğin
    kendi çalışma saatine çevrilir (lastik makineler arasında taşınabildiği için)."""
    with ctx.tx() as conn:
        t = conn.execute(
            """select th.id, th.hours_total, th.otd_mm, th.scrap_tread_mm, th.tread_mm,
                      th.projected_hours_left, th.wear_mm_per_hour, th.status,
                      pi.installed_at_hours, pi.hours_accumulated
                 from public.v_tire_health th join public.part_items pi on pi.id = th.id
                where th.id = %s and th.tenant_id = %s""",
            [part_id, ctx.tenant_id],
        ).fetchone()
        if not t:
            raise HTTPException(404, "Lastik bulunamadı")
        rows = conn.execute(
            """select m.value, m.asset_hours, m.measured_at from public.measurements m
                 left join public.inspections i on i.id = m.inspection_id
                where m.part_item_id = %s and m.metric = 'tread_depth_mm'
                  and (m.inspection_id is null or i.status = 'completed')
                order by m.measured_at""",
            [part_id],
        ).fetchall()

    points = [{"part_hours": 0, "tread_mm": t["otd_mm"], "kind": "new", "measured_at": None}]
    for r in rows:
        # Yalnızca mevcut montajdaki ölçümler parça saatine güvenle çevrilebilir
        if (t["status"] == "installed" and r["asset_hours"] is not None
                and t["installed_at_hours"] is not None and r["asset_hours"] >= t["installed_at_hours"]):
            ph = t["hours_accumulated"] + (r["asset_hours"] - t["installed_at_hours"])
            points.append({"part_hours": ph, "tread_mm": r["value"], "kind": "measured",
                           "measured_at": r["measured_at"]})
    projection = None
    if t["projected_hours_left"] is not None and t["tread_mm"] is not None:
        projection = {"from_hours": t["hours_total"], "from_mm": t["tread_mm"],
                      "to_hours": t["hours_total"] + t["projected_hours_left"], "to_mm": t["scrap_tread_mm"]}
    return {"otd_mm": t["otd_mm"], "scrap_tread_mm": t["scrap_tread_mm"], "hours_total": t["hours_total"],
            "wear_mm_per_hour": t["wear_mm_per_hour"], "points": points, "projection": projection}


@router.get("/reports/tire-cost", summary="Makine başına lastik maliyeti (saat başı, ömür sonu beklenen)")
def tire_cost(ctx: TenantCtx):
    with ctx.tx() as conn:
        return conn.execute(
            """select a.id as asset_id, a.code,
                      count(th.id) as tires,
                      count(th.expected_cost_per_hour) as tires_with_data,
                      round(sum(th.expected_cost_per_hour), 2) as expected_cost_per_hour
                 from public.assets a
                 join public.v_tire_health th on th.current_asset_id = a.id and th.status = 'installed'
                where a.tenant_id = %s
                group by a.id, a.code
                order by expected_cost_per_hour desc nulls last""",
            [ctx.tenant_id],
        ).fetchall()


@router.get("/reports/fleet.pdf", summary="PDF durum raporu (tüm filo, bir saha veya tek makine)",
            response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def fleet_pdf(ctx: TenantCtx, storage: AppStorage, asset_id: UUID | None = None, site_id: UUID | None = None):
    from ..report import Scope, gather, render

    with ctx.tx() as conn:
        if asset_id and not conn.execute(
            "select 1 from public.assets where id = %s and tenant_id = %s", [asset_id, ctx.tenant_id]
        ).fetchone():
            raise HTTPException(404, "Makine bulunamadı")
        data = gather(conn, storage, ctx.tenant_id, ctx.user_id, Scope(asset_id=asset_id, site_id=site_id))
    pdf = render(data)
    stamp = data["now"].strftime("%Y-%m-%d")
    name = f"sparetwin-{data['assets'][0]['code']}-{stamp}.pdf" if asset_id and data["assets"] else f"sparetwin-filo-raporu-{stamp}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/parts/{part_id}/measurements", summary="Ölçüm geçmişi (grafik için)")
def part_measurements(part_id: UUID, ctx: TenantCtx, metric: str | None = None):
    with ctx.tx() as conn:
        return conn.execute(
            """select m.metric, m.value, m.unit, m.source, m.asset_hours, m.measured_at, m.inspection_id,
                      i.status::text as inspection_status
                 from public.measurements m
                 left join public.inspections i on i.id = m.inspection_id
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
