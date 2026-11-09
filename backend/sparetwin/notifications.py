"""Bildirimler: her istekte güncel veriden üretilir, saklanmaz.

Her bildirimin durumunu içeren bir anahtarı vardır; durum değişince anahtar
değişir ve bildirim yeniden okunmamış olur. Sunucu aşamasında e-posta
bildirimleri de bu listeyi (collect) kullanacak.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import psycopg

from .tenant_settings import thresholds

CAT_TR = {"tire": "lastik", "rim": "jant", "hyd_cylinder": "hidrolik silindir", "hyd_pump": "hidrolik pompa",
          "battery": "akü", "filter": "filtre"}


def _n(v: Any) -> str:
    return "–" if v is None else f"{float(v):,.0f}".replace(",", ".")


def collect(conn: psycopg.Connection, tenant_id: UUID) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    stale_days = int(thresholds(conn, tenant_id)["inspection_interval_days"])  # firma ayarı (0013)

    # 1) Kritik parçalar
    for p in conn.execute(
        """select ph.id, ph.asset_code, ph.current_position, ph.category_code, ph.condition_pct,
                  ph.projected_hours_left, (l.latest_measurements->'tread_depth_mm'->>'at')::timestamptz as measured_at
             from public.v_part_health ph join public.v_part_items_live l on l.id = ph.id
            where ph.tenant_id = %s and ph.status = 'installed' and ph.band = 'critical'""", [tenant_id]).fetchall():
        is_tire = p["category_code"] == "tire"
        body = (f"Diş %{_n(p['condition_pct'])}" + (f" · yaklaşık {_n(p['projected_hours_left'])} saat kaldı"
                                                    if p["projected_hours_left"] is not None else "")
                if is_tire else ("Beklenen ömrünü aştı" if (p["condition_pct"] or 0) <= 0
                                 else f"Ömrün %{_n(100 - float(p['condition_pct']))} kadarı kullanıldı"))
        out.append({
            "key": f"part:{p['id']}:critical:{p['measured_at'].isoformat() if p['measured_at'] else ''}",
            "kind": "part_critical", "severity": "critical",
            "title": f"{p['asset_code']} {p['current_position']} {CAT_TR.get(p['category_code'], 'parça')} kritik",
            "body": body, "link": {"type": "part", "id": str(p["id"])}, "at": p["measured_at"]})

    # 2) Jant muayenesi
    for r in conn.execute(
        """select r.id, r.serial_no, r.asset_code, r.current_position, r.compliance, r.hours_since_ndt,
                  r.ndt_interval_hours, r.last_ndt_hours
             from public.v_rim_compliance r
            where r.tenant_id = %s and r.compliance in ('overdue', 'due_soon')""", [tenant_id]).fetchall():
        where = f"{r['asset_code']} {r['current_position']}" if r["asset_code"] else f"Stoktaki jant {r['serial_no'] or ''}"
        overdue = r["compliance"] == "overdue"
        out.append({
            "key": f"rim:{r['id']}:{r['compliance']}:{r['last_ndt_hours']}",
            "kind": "rim_ndt", "severity": "critical" if overdue else "watch",
            "title": f"{where} jant muayenesi {'gecikti' if overdue else 'yaklaşıyor'}",
            "body": f"Son muayeneden bu yana {_n(r['hours_since_ndt'])} / {_n(r['ndt_interval_hours'])} saat",
            "link": {"type": "rim", "id": str(r["id"])}, "at": None})

    # 3) Kritik seviyenin altındaki stok
    for s in conn.execute(
        """select part_id as id, name, min_stock, qty as in_stock, unit from public.v_stock_totals
            where tenant_id = %s and min_stock > 0 and below_min""", [tenant_id]).fetchall():
        qty = f"{float(s['in_stock']):g}".replace(".", ",")
        out.append({
            "key": f"stock:{s['id']}:{s['in_stock']}", "kind": "stock_low", "severity": "watch",
            "title": f"{s['name']} stoğu düşük",
            "body": f"Depoda {qty} {s['unit']}, kritik seviye {s['min_stock']}",
            "link": {"type": "stock", "id": str(s["id"])}, "at": None})

    # 4) Uzun süredir kontrol edilmeyen makineler
    limit = datetime.now(timezone.utc) - timedelta(days=stale_days)
    for a in conn.execute(
        """select a.id, a.code, a.created_at,
                  (select max(i.completed_at) from public.inspections i
                    where i.asset_id = a.id and i.status = 'completed') as last
             from public.assets a where a.tenant_id = %s and a.status <> 'retired'""", [tenant_id]).fetchall():
        ref = a["last"] or a["created_at"]
        if ref < limit:
            days = (datetime.now(timezone.utc) - ref).days
            out.append({
                "key": f"stale:{a['id']}:{a['last'].date().isoformat() if a['last'] else 'never'}",
                "kind": "asset_stale", "severity": "watch",
                "title": f"{a['code']} {days} gündür kontrol edilmedi" if a["last"] else f"{a['code']} hiç kontrol edilmedi",
                "body": f"Saha kontrolü {stale_days} günde bir önerilir",
                "link": {"type": "asset", "id": str(a["id"])}, "at": a["last"]})

    # 5) Lastiği takılı ama jantı kaydedilmemiş pozisyonlar (muayene takibi yapılamıyor)
    for g in conn.execute(
        """select a.id, a.code, count(*) as n
             from public.assets a
             join public.asset_models am on am.id = a.model_id
             join public.template_positions tp on tp.template_id = am.template_id and tp.category_code = 'rim'
             join public.part_items t on t.current_asset_id = a.id and t.status = 'installed'
                  and t.current_position = left(tp.code, length(tp.code) - 2)
            where a.tenant_id = %s
              and not exists (select 1 from public.part_items r where r.current_asset_id = a.id
                                 and r.current_position = tp.code and r.status = 'installed')
            group by a.id, a.code""", [tenant_id]).fetchall():
        out.append({
            "key": f"rimgap:{g['id']}:{g['n']}", "kind": "rim_missing", "severity": "watch",
            "title": f"{g['code']}: {g['n']} jant kaydı yok",
            "body": "Lastiği takılı ama jantı kaydedilmemiş pozisyonlar var; bu jantların muayenesi takip edilmiyor",
            "link": {"type": "asset", "id": str(g["id"])}, "at": None})

    order = {"critical": 0, "watch": 1}
    out.sort(key=lambda n: (order[n["severity"]], n["title"]))
    return out
