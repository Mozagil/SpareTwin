"""Makine toplam sahip olma maliyeti (TCO) raporu (Faz 2).

Parça + sarf + işçilik + dış servis + duruş, makine başına ve seçilen dönem için.
Hesap veritabanında (0016 / 0017, public.asset_tco); burada yalnızca dönem, saha süzgeci ve filo toplamı.
Excel ve PDF çıktısı aynı veriden üretilir (tco_export).
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import Response

from ..tenant_settings import thresholds
from .deps import TenantCtx

router = APIRouter(prefix="/reports", tags=["Raporlar"])

COST_KEYS = ("parts_cost", "consumables_cost", "labor_cost", "external_cost", "downtime_cost", "total")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
Months = Query(12, ge=1, le=60, description="Geriye dönük dönem (ay)")


def _report(conn, ctx: TenantCtx, months: int, site_id: UUID | None) -> dict[str, Any]:
    now = datetime.now().astimezone()
    start = now - timedelta(days=round(months * 365 / 12))
    rows = conn.execute(
        """select * from public.asset_tco(%(t)s, %(from)s, %(to)s)
            where (%(s)s::uuid is null or site_id = %(s)s)
              and (asset_status <> 'retired' or total > 0)
            order by total desc, asset_code""",
        {"t": ctx.tenant_id, "from": start, "to": now, "s": site_id},
    ).fetchall()
    settings = conn.execute("select settings from public.tenants where id = %s", [ctx.tenant_id]).fetchone()
    rate = thresholds(conn, ctx.tenant_id)["downtime_cost_per_hour"]
    totals: dict = {k: sum((r[k] for r in rows), Decimal(0)) for k in COST_KEYS}
    totals["downtime_minutes"] = sum(r["downtime_minutes"] for r in rows)
    totals["hours_worked"] = sum((r["hours_worked"] for r in rows), Decimal(0))
    totals["cost_per_hour"] = round(totals["total"] / totals["hours_worked"], 2) if totals["hours_worked"] > 0 else None
    return {
        "months": months, "from": start, "to": now,
        "currency": ((settings or {}).get("settings") or {}).get("currency", "USD"),
        "downtime_cost_per_hour": rate,
        "totals": totals,
        "assets": rows,
    }


def _export(ctx: TenantCtx, months: int, site_id: UUID | None) -> dict[str, Any]:
    """Rapor + çıktının başlığında görünen firma, saha ve hazırlayan."""
    with ctx.tx() as conn:
        rep = _report(conn, ctx, months, site_id)
        rep["tenant"] = conn.execute("select name from public.tenants where id = %s", [ctx.tenant_id]).fetchone()["name"]
        user = conn.execute("select coalesce(full_name, email) as n from public.app_users where id = %s", [ctx.user_id]).fetchone()
        rep["user"] = user["n"] if user else ""
        site = conn.execute("select name from public.sites where id = %s and tenant_id = %s", [site_id, ctx.tenant_id]).fetchone() \
            if site_id else None
        rep["site"] = site["name"] if site else None
    return rep


def _attachment(content: bytes, media_type: str, rep: dict[str, Any], ext: str) -> Response:
    name = f"sparetwin-maliyet-{rep['months']}ay-{rep['to'].strftime('%Y-%m-%d')}.{ext}"
    return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/tco", summary="Makine toplam sahip olma maliyeti: parça, sarf, işçilik, dış servis, duruş")
def tco(ctx: TenantCtx, months: int = Months, site_id: UUID | None = None):
    with ctx.tx() as conn:
        return _report(conn, ctx, months, site_id)


@router.get("/tco.xlsx", summary="Maliyet raporu, Excel", response_class=Response,
            responses={200: {"content": {XLSX: {}}}})
def tco_xlsx(ctx: TenantCtx, months: int = Months, site_id: UUID | None = None):
    from ..tco_export import xlsx

    rep = _export(ctx, months, site_id)
    return _attachment(xlsx(rep), XLSX, rep, "xlsx")


@router.get("/tco.pdf", summary="Maliyet raporu, PDF", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
def tco_pdf(ctx: TenantCtx, months: int = Months, site_id: UUID | None = None):
    from ..tco_export import pdf

    rep = _export(ctx, months, site_id)
    return _attachment(pdf(rep), "application/pdf", rep, "pdf")
