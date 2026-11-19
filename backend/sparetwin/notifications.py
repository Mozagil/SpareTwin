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

STALE_DAYS = 30  # varsayılan; firma ayarı (inspection_interval_days) önceliklidir
CAT_TR = {"tire": "lastik", "rim": "jant", "hyd_cylinder": "hidrolik silindir", "hyd_pump": "hidrolik pompa",
          "battery": "akü", "filter": "filtre"}


DOWNTIME_TR = {"breakdown": "Arıza", "planned_maintenance": "Planlı bakım", "tire": "Lastik", "waiting_parts": "Parça bekleniyor",
               "operational": "Operasyonel", "other": "Diğer"}


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

    # 3) Kritik seviyenin altındaki stok (siparişte olan varsa söylenir; anahtar değişir)
    for s in conn.execute(
        """select st.part_id as id, st.name, st.min_stock, st.qty as in_stock, st.unit, coalesce(oo.on_order, 0) as on_order
             from public.v_stock_totals st
             left join public.v_purchase_on_order oo on oo.tenant_id = st.tenant_id and oo.part_id = st.part_id
            where st.tenant_id = %s and st.min_stock > 0 and st.below_min""", [tenant_id]).fetchall():
        qty = f"{float(s['in_stock']):g}".replace(".", ",")
        on_order = f"{float(s['on_order']):g}".replace(".", ",")
        out.append({
            "key": f"stock:{s['id']}:{s['in_stock']}:{s['on_order']}", "kind": "stock_low", "severity": "watch",
            "title": f"{s['name']} stoğu düşük",
            "body": f"Depoda {qty} {s['unit']}, kritik seviye {s['min_stock']}"
                    + (f", siparişte {on_order} {s['unit']}" if float(s["on_order"]) > 0 else ""),
            "link": {"type": "stock", "id": str(s["id"])}, "at": None})

    # 4) Uzun süredir kontrol edilmeyen makineler (firma ayarı)
    from .api.settings import get_settings
    stale_days = get_settings(conn, tenant_id)["inspection_interval_days"]
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

    # 7) Bakım planları: geciken ve yaklaşan
    for m in conn.execute(
        """select id, asset_id, asset_code, name, due_status, hours_left, days_left, last_done_at, last_done_hours
             from public.v_maintenance_due where tenant_id = %s and due_status in ('overdue', 'due_soon')""",
        [tenant_id]).fetchall():
        overdue = m["due_status"] == "overdue"
        parts = []
        if m["hours_left"] is not None:
            parts.append(f"{_n(-m['hours_left'])} saat gecikti" if m["hours_left"] < 0 else f"{_n(m['hours_left'])} saat kaldı")
        if m["days_left"] is not None:
            parts.append(f"{-m['days_left']} gün gecikti" if m["days_left"] < 0 else f"{m['days_left']} gün kaldı")
        out.append({
            "key": f"maint:{m['id']}:{m['due_status']}:{m['last_done_hours']}:{m['last_done_at'].date() if m['last_done_at'] else ''}",
            "kind": "maintenance_due", "severity": "critical" if overdue else "watch",
            "title": f"{m['asset_code']}: {m['name']} {'gecikti' if overdue else 'yaklaşıyor'}",
            "body": " · ".join(parts) or "Hiç yapılmadı",
            "link": {"type": "maintenance", "id": str(m["id"])}, "at": None})

    # 8) Süren duruşlar
    for d in conn.execute(
        """select d.id, d.asset_id, a.code, d.category, d.description, d.started_at
             from public.downtime_events d join public.assets a on a.id = d.asset_id
            where d.tenant_id = %s and d.ended_at is null""", [tenant_id]).fetchall():
        h = (datetime.now(timezone.utc) - d["started_at"]).total_seconds() / 3600
        dur = f"{h:.0f} saattir" if h < 48 else f"{h / 24:.0f} gündür"
        out.append({
            "key": f"down:{d['id']}", "kind": "downtime_open", "severity": "critical",
            "title": f"{d['code']} {dur} duruşta",
            "body": d["description"] or DOWNTIME_TR.get(d["category"], d["category"]),
            "link": {"type": "asset", "id": str(d["asset_id"])}, "at": d["started_at"]})

    # 6) Teslimatı geciken siparişler
    for po in conn.execute(
        """select po.id, po.number, po.expected_date, s.name as supplier,
                  count(*) filter (where l.received_qty < l.qty) as open_lines
             from public.purchase_orders po
             left join public.suppliers s on s.id = po.supplier_id
             join public.purchase_order_lines l on l.po_id = po.id
            where po.tenant_id = %s and po.status in ('ordered', 'partial') and po.expected_date < current_date
            group by po.id, s.name""", [tenant_id]).fetchall():
        days = (datetime.now(timezone.utc).date() - po["expected_date"]).days
        out.append({
            "key": f"po_late:{po['id']}:{po['expected_date'].isoformat()}", "kind": "po_late", "severity": "watch",
            "title": f"{po['number']} teslimatı {days} gün gecikti",
            "body": f"{po['supplier'] or 'Tedarikçi yok'} · {po['open_lines']} kalem bekleniyor",
            "link": {"type": "po", "id": str(po["id"])}, "at": None})

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

    # Kapalı modüllerin bildirimleri gösterilmez
    from .api.settings import get_settings
    mods = get_settings(conn, tenant_id)["modules"]
    hidden = set()
    if not mods["tireiq"]:
        hidden |= {"rim_ndt", "rim_missing"}
    if not mods["parts"]:
        hidden |= {"stock_low", "po_late", "maintenance_due", "downtime_open"}
    out = [n for n in out if n["kind"] not in hidden]

    order = {"critical": 0, "watch": 1}
    out.sort(key=lambda n: (order[n["severity"]], n["title"]))
    return out
