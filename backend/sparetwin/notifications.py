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

    # 3b) Yaklaşan değişim için sipariş ihtiyacı: "LD-07 için 2 lastik yaklaşıyor, stokta 1 var"
    for n in conn.execute(
        """select part_id as id, name, unit, category_code, upcoming, items, in_stock, on_order, requested, need
             from public.v_purchase_needs where tenant_id = %s and upcoming > 0 and need > 0""", [tenant_id]).fetchall():
        assets = sorted({i["asset_code"] for i in (n["items"] or []) if i.get("asset_code")})
        where = ", ".join(assets[:3]) + (" ve diğerleri" if len(assets) > 3 else "")
        cat = CAT_TR.get(n["category_code"], "parça")
        stock_txt = f"stokta {_n(n['in_stock'])} var" if float(n["in_stock"]) > 0 else "stokta yok"
        extra = (f", siparişte {_n(n['on_order'])}" if float(n["on_order"]) > 0 else "") + \
                (f", talepte {_n(n['requested'])}" if float(n["requested"]) > 0 else "")
        out.append({
            "key": f"need:{n['id']}:{n['upcoming']}:{n['in_stock']}:{n['on_order']}", "kind": "purchase_need", "severity": "watch",
            "title": f"{where} için {n['upcoming']} {cat} yaklaşıyor, {stock_txt}",
            "body": f"{n['name']}: önerilen sipariş {_n(n['need'])} {n['unit']}{extra}",
            "link": {"type": "purchasing", "id": str(n["id"])}, "at": None})

    # 3c) Teslimatı geciken siparişler
    for o in conn.execute(
        """select o.id, o.number, o.expected_at, s.name as supplier, current_date - o.expected_at as late_days
             from public.purchase_orders o left join public.suppliers s on s.id = o.supplier_id
            where o.tenant_id = %s and o.status in ('ordered', 'partial') and o.expected_at < current_date""", [tenant_id]).fetchall():
        out.append({
            "key": f"po:{o['id']}:late:{o['expected_at'].isoformat()}", "kind": "po_late", "severity": "watch",
            "title": f"{o['number']} teslimatı gecikti",
            "body": f"{o['supplier'] or 'Tedarikçi'}, beklenen {o['expected_at'].strftime('%d.%m.%Y')}, {o['late_days']} gün gecikme",
            "link": {"type": "order", "id": str(o["id"])}, "at": None})

    # 3d) Sıradaki bakım yaklaşıyor ya da gecikti (açık emri olanlar emir listesinde zaten görünür)
    for m in conn.execute(
        """select plan_id, asset_id, asset_code, name, state, interval_hours, interval_days, meter_hours,
                  last_done_hours, last_done_at, next_due_hours, next_due_at, hours_left, days_left, eta_at
             from public.v_maintenance_due
            where tenant_id = %s and state in ('overdue', 'due_soon') and open_work_order_id is null""", [tenant_id]).fetchall():
        overdue = m["state"] == "overdue"
        parts = []
        if m["next_due_hours"] is not None:
            parts.append(f"sıradaki {_n(m['next_due_hours'])} saatte, makine {_n(m['meter_hours'])} saatte"
                         + (f" ({_n(-m['hours_left'])} saat geçti)" if m["hours_left"] < 0 else f" ({_n(m['hours_left'])} saat kaldı)"))
        if m["next_due_at"] is not None:
            parts.append(f"tarih {m['next_due_at'].strftime('%d.%m.%Y')}"
                         + (f" ({-m['days_left']} gün geçti)" if m["days_left"] < 0 else f" ({m['days_left']} gün kaldı)"))
        last = (f"Son bakım {_n(m['last_done_hours'])} saatte" if m["last_done_hours"] is not None
                else f"Son bakım {m['last_done_at'].strftime('%d.%m.%Y')}" if m["last_done_at"] else "Hiç yapılmadı")
        out.append({
            "key": f"maint:{m['plan_id']}:{m['asset_id']}:{m['state']}:{m['next_due_hours']}:{m['next_due_at']}",
            "kind": "maintenance_due", "severity": "critical" if overdue else "watch",
            "title": f"{m['asset_code']} {m['name']} {'gecikti' if overdue else 'yaklaşıyor'}",
            "body": f"{last}; " + "; ".join(parts),
            "link": {"type": "maintenance", "id": str(m["asset_id"])}, "at": None})

    # 3e) Arızalı makineler: açık arıza emri
    for w in conn.execute(
        """select w.id, w.number, w.title, w.status, w.reason_code, a.code,
                  round(extract(epoch from (now() - w.down_from)) / 3600) as down_hours
             from public.work_orders w join public.assets a on a.id = w.asset_id
            where w.tenant_id = %s and w.kind = 'breakdown' and w.status in ('open', 'in_progress')""", [tenant_id]).fetchall():
        out.append({
            "key": f"down:{w['id']}:{w['status']}", "kind": "asset_down", "severity": "critical",
            "title": f"{w['code']} arızalı: {w['title']}",
            "body": f"{w['number']} · {'onarım sürüyor' if w['status'] == 'in_progress' else 'onarım bekliyor'}"
                    + (f" · {_n(w['down_hours'])} saattir duruyor" if (w["down_hours"] or 0) >= 1 else " · 1 saatten kısa süredir duruyor"),
            "link": {"type": "work_order", "id": str(w["id"])}, "at": None})

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
