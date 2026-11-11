"""Bakım: planlar, sıradaki bakımlar, planlı emir akışı (stoktan düşme, sayaç), arıza ve duruş, bildirim, denetim."""

from datetime import date, datetime, timedelta, timezone


PLAN_500 = "81111111-0000-0000-0000-000000000001"   # L220H modeli, 500 saat
PLAN_RS = "81111111-0000-0000-0000-000000000002"    # RS-02, 180 gün
LD07 = "41111111-0000-0000-0000-000000000001"       # 12.480 saat, son bakım 12.000
LD09 = "41111111-0000-0000-0000-000000000002"       # 6.210 saat, son bakım 6.000
RS02 = "41111111-0000-0000-0000-000000000003"
FL14 = "41111111-0000-0000-0000-000000000004"
L220H = "31111111-0000-0000-0000-000000000001"
FILTER = "51111111-0000-0000-0000-000000000011"     # Soma'da 4 adet
OIL = "51111111-0000-0000-0000-000000000012"        # Soma'da 280 litre
TIRE = "51111111-0000-0000-0000-000000000001"       # seri numaralı
SOMA = "21111111-0000-0000-0000-000000000002"
YEAR = date.today().year


def due_row(client, h, plan, asset):
    return next(d for d in client.get("/maintenance/due", headers=h).json() if d["plan_id"] == plan and d["asset_id"] == asset)


def asset_status(client, h, asset):
    return client.get(f"/assets/{asset}", headers=h).json()["status"]


def site_qty(client, h, part, site):
    row = next(s for s in client.get("/stock", headers=h).json() if s["part_id"] == part)
    return float(next((s["qty"] for s in row["sites"] or [] if s["site_id"] == site), 0))


def notif(client, h, kind):
    return [n for n in client.get("/notifications", headers=h).json()["items"] if n["kind"] == kind]


def test_planlar_ve_yetki(client, manager, tech):
    rows = {p["id"]: p for p in client.get("/maintenance/plans", headers=tech).json()}
    p500 = rows[PLAN_500]
    assert p500["asset_count"] == 2 and p500["model_name"] == "Volvo L220H" and float(p500["interval_hours"]) == 500
    assert {(x["part_id"], float(x["qty"])) for x in p500["parts"]} == {(FILTER, 4), (OIL, 60)}
    assert len(p500["checklist"]) == 4
    # Makineye göre: LD-07 model planını görür, RS-02 planını görmez
    ids = {p["id"] for p in client.get("/maintenance/plans", headers=tech, params={"asset_id": LD07}).json()}
    assert PLAN_500 in ids and PLAN_RS not in ids

    body = {"name": "Aylık genel kontrol", "model_id": L220H, "interval_days": 30, "checklist": ["Kaçak kontrolü", " ", "Sıkma torku"]}
    assert client.post("/maintenance/plans", headers=tech, json=body).status_code == 403
    r = client.post("/maintenance/plans", headers=manager, json=body)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["checklist"] == ["Kaçak kontrolü", "Sıkma torku"] and r.json()["asset_count"] == 2
    # Kurallar: kapsam ikisinden biri, periyot şart, seri numaralı parça sarf listesine girmez
    assert client.post("/maintenance/plans", headers=manager, json={**body, "asset_id": LD07}).status_code == 422
    assert client.post("/maintenance/plans", headers=manager, json={"name": "x y", "model_id": L220H}).status_code == 422
    assert client.post("/maintenance/plans", headers=manager,
                       json={**body, "parts": [{"part_id": TIRE, "qty": 1}]}).status_code == 422
    r = client.patch(f"/maintenance/plans/{pid}", headers=manager, json={**body, "is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert pid not in {p["id"] for p in client.get("/maintenance/plans", headers=manager).json()}
    assert pid in {p["id"] for p in client.get("/maintenance/plans", headers=manager, params={"include_inactive": True}).json()}


def test_siradaki_bakimlar_ve_esik(client, manager):
    ld07 = due_row(client, manager, PLAN_500, LD07)
    assert float(ld07["last_done_hours"]) == 12000 and float(ld07["next_due_hours"]) == 12500
    assert float(ld07["hours_left"]) == 20 and ld07["state"] == "due_soon" and ld07["last_done_number"] == f"BK-{YEAR}-0001"
    ld09 = due_row(client, manager, PLAN_500, LD09)
    assert float(ld09["next_due_hours"]) == 6500 and float(ld09["hours_left"]) == 290 and ld09["state"] == "ok"
    rs = due_row(client, manager, PLAN_RS, RS02)
    assert rs["days_left"] == 5 and rs["state"] == "due_soon" and rs["next_due_at"] == str(date.today() + timedelta(days=5))
    assert rs["last_done_at"] is None and rs["eta_at"] == rs["next_due_at"]
    # Sıralama: yaklaşanlar önce
    states = [d["state"] for d in client.get("/maintenance/due", headers=manager).json()]
    assert states == sorted(states, key=lambda s: {"overdue": 0, "due_soon": 1, "ok": 2}[s])
    assert {d["asset_id"] for d in client.get("/maintenance/due", headers=manager, params={"state": "due_soon"}).json()} == {LD07, RS02}

    items = notif(client, manager, "maintenance_due")
    t = {n["title"] for n in items}
    assert "LD-07 500 saat periyodik bakım yaklaşıyor" in t and "RS-02 6 aylık hidrolik sistem bakımı yaklaşıyor" in t
    ld = next(n for n in items if n["title"].startswith("LD-07"))
    assert ld["severity"] == "watch" and "Son bakım 12.000 saatte" in ld["body"] and "20 saat kaldı" in ld["body"]
    assert ld["link"] == {"type": "maintenance", "id": LD07}

    # Eşik firmaya göre: 10 saate çekilince LD-07 artık "yaklaşıyor" değil
    r = client.patch("/organization", headers=manager, json={"thresholds": {"maint_warn_hours": 10}})
    assert r.status_code == 200, r.text
    assert due_row(client, manager, PLAN_500, LD07)["state"] == "ok"
    assert not [n for n in notif(client, manager, "maintenance_due") if n["title"].startswith("LD-07")]
    client.patch("/organization", headers=manager, json={"thresholds": {"maint_warn_hours": 50}})
    assert client.patch("/organization", headers=manager, json={"thresholds": {"maint_warn_days": 0}}).status_code == 422


def test_planli_emir_akisi(client, manager, tech):
    assert client.post("/maintenance/work-orders", headers=tech, json={"asset_id": LD07}).status_code == 422  # plan ya da başlık
    r = client.post("/maintenance/work-orders", headers=tech, json={"asset_id": LD07, "plan_id": PLAN_500})
    assert r.status_code == 201, r.text
    w = r.json()
    wid = w["id"]
    assert w["number"] == f"BK-{YEAR}-0004" and w["title"] == "500 saat periyodik bakım" and w["status"] == "open"
    assert float(w["due_hours"]) == 12500 and w["late"] is False and len(w["checklist"]) == 4
    assert {(p["part_id"], float(p["qty"]), p["site_id"]) for p in w["parts"]} == {(FILTER, 4, SOMA), (OIL, 60, SOMA)}
    assert float(next(p for p in w["parts"] if p["part_id"] == FILTER)["in_stock"]) == 4
    # Açık emri olan bakım bildirimden düşer, takvimde emir görünür
    d = due_row(client, tech, PLAN_500, LD07)
    assert d["open_work_order_id"] == wid and d["open_work_order_status"] == "open"
    assert not [n for n in notif(client, tech, "maintenance_due") if n["title"].startswith("LD-07")]

    # Başla → makine bakımda
    r = client.post(f"/maintenance/work-orders/{wid}/status", headers=tech, json={"status": "in_progress"})
    assert r.status_code == 200 and r.json()["status"] == "in_progress" and r.json()["started_at"]
    assert asset_status(client, tech, LD07) == "maintenance"
    assert client.post(f"/maintenance/work-orders/{wid}/status", headers=tech, json={"status": "in_progress"}).status_code == 422

    # Tamamla: sarf stoktan düşer, sayaç ilerler, makine çalışmaya döner
    r = client.post(f"/maintenance/work-orders/{wid}/status", headers=tech,
                    json={"status": "done", "asset_hours": 12510, "labor_cost": 300, "notes": "Filtreler ve yağ değişti"})
    assert r.status_code == 200, r.text
    w = r.json()
    assert w["status"] == "done" and float(w["asset_hours_at_done"]) == 12510 and float(w["labor_cost"]) == 300
    assert w["completed_by_name"] == "Demo Teknisyen" and "Filtreler ve yağ değişti" in w["description"]
    assert float(next(p for p in w["parts"] if p["part_id"] == FILTER)["unit_cost"]) == 82
    assert asset_status(client, tech, LD07) == "active"
    assert float(client.get(f"/assets/{LD07}", headers=tech).json()["meter_hours"]) == 12510
    assert site_qty(client, tech, FILTER, SOMA) == 0 and site_qty(client, tech, OIL, SOMA) == 220
    mv = client.get(f"/stock/{FILTER}/movements", headers=tech).json()[0]
    assert mv["ref"] == f"BK-{YEAR}-0004" and mv["reason"] == "periyodik bakım" and float(mv["qty"]) == -4
    d = due_row(client, tech, PLAN_500, LD07)
    assert float(d["next_due_hours"]) == 13010 and float(d["hours_left"]) == 500 and d["state"] == "ok" and d["open_work_order_id"] is None
    assert client.post(f"/maintenance/work-orders/{wid}/status", headers=tech, json={"status": "done"}).status_code == 422
    assert client.patch(f"/maintenance/work-orders/{wid}", headers=tech, json={"title": "değişmez"}).status_code == 422

    s = next(x for x in client.get("/maintenance/summary", headers=tech).json() if x["asset_id"] == LD07)
    assert s["planned_done"] == 2 and s["breakdowns"] == 0 and float(s["cost_12m"]) > 821 + 300

    # Stok yetmezse tamamlanamaz; iptal yöneticinin
    r = client.post("/maintenance/work-orders", headers=tech, json={"asset_id": LD09, "plan_id": PLAN_500, "due_at": str(date.today())})
    w2 = r.json()["id"]
    r = client.post(f"/maintenance/work-orders/{w2}/status", headers=tech, json={"status": "done"})
    assert r.status_code == 422 and "Stokta yeterli yok" in r.json()["detail"]
    assert asset_status(client, tech, LD09) == "active"
    assert client.post(f"/maintenance/work-orders/{w2}/status", headers=tech, json={"status": "cancelled"}).status_code == 403
    r = client.post(f"/maintenance/work-orders/{w2}/status", headers=manager, json={"status": "cancelled"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    listed = client.get("/maintenance/work-orders", headers=tech, params={"open_only": True}).json()
    assert w2 not in {x["id"] for x in listed} and wid not in {x["id"] for x in listed}
    assert {x["status"] for x in client.get("/maintenance/work-orders", headers=tech, params={"status": "cancelled"}).json()} == {"cancelled"}


def test_ariza_emri_ve_durus(client, manager, tech):
    assert client.post("/maintenance/work-orders", headers=tech, json={"asset_id": FL14, "kind": "breakdown"}).status_code == 422
    down_from = datetime.now(timezone.utc) - timedelta(hours=2)
    r = client.post("/maintenance/work-orders", headers=tech, json={
        "asset_id": FL14, "kind": "breakdown", "title": "Hidrolik hortum patladı", "reason_code": "hydraulic",
        "down_from": down_from.isoformat(), "parts": [{"part_id": OIL, "qty": 20, "site_id": "21111111-0000-0000-0000-000000000001"}]})
    assert r.status_code == 201, r.text
    w = r.json()
    wid = w["id"]
    assert w["kind"] == "breakdown" and w["down_to"] is None and w["downtime_minutes"] is None
    assert asset_status(client, tech, FL14) == "down"
    items = notif(client, tech, "asset_down")
    assert len(items) == 1 and items[0]["title"] == "FL-14 arızalı: Hidrolik hortum patladı" and items[0]["severity"] == "critical"
    assert "onarım bekliyor" in items[0]["body"] and "2 saattir duruyor" in items[0]["body"]
    assert items[0]["link"] == {"type": "work_order", "id": wid}
    assert [x["id"] for x in client.get("/maintenance/work-orders", headers=tech, params={"kind": "breakdown", "open_only": True}).json()] == [wid]
    first = client.get("/maintenance/work-orders", headers=tech, params={"open_only": True}).json()[0]
    assert first["id"] == wid  # arıza listede en üstte

    client.post(f"/maintenance/work-orders/{wid}/status", headers=tech, json={"status": "in_progress"})
    assert asset_status(client, tech, FL14) == "down"
    assert "onarım sürüyor" in notif(client, tech, "asset_down")[0]["body"]
    # Dönüş, duruştan önce olamaz
    bad = client.post(f"/maintenance/work-orders/{wid}/status", headers=tech,
                      json={"status": "done", "down_to": (down_from - timedelta(hours=1)).isoformat()})
    assert bad.status_code == 422
    r = client.post(f"/maintenance/work-orders/{wid}/status", headers=tech,
                    json={"status": "done", "down_to": datetime.now(timezone.utc).isoformat(), "external_cost": 450})
    assert r.status_code == 200, r.text
    w = r.json()
    assert w["status"] == "done" and 118 <= w["downtime_minutes"] <= 125 and float(w["external_cost"]) == 450
    assert asset_status(client, tech, FL14) == "active" and not notif(client, tech, "asset_down")
    assert site_qty(client, tech, OIL, "21111111-0000-0000-0000-000000000001") == 60
    s = next(x for x in client.get("/maintenance/summary", headers=tech).json() if x["asset_id"] == FL14)
    assert s["breakdowns"] == 2 and 300 + 118 <= s["downtime_minutes"] <= 300 + 125


def test_izolasyon_ve_denetim(client, manager, other):
    assert client.get("/maintenance/plans", headers=other).json() == []
    assert client.get("/maintenance/due", headers=other).json() == []
    assert client.get("/maintenance/work-orders", headers=other).json() == []
    wid = client.get("/maintenance/work-orders", headers=manager).json()[0]["id"]
    assert client.get(f"/maintenance/work-orders/{wid}", headers=other).status_code == 404
    assert client.post(f"/maintenance/work-orders/{wid}/status", headers=other, json={"status": "cancelled"}).status_code == 404
    assert client.post("/maintenance/work-orders", headers=other, json={"asset_id": LD07, "title": "başkasının makinesi"}).status_code == 404

    rows = [r for r in client.get("/audit", headers=manager, params={"limit": 500}).json() if r["entity_type"] == "maintenance"]
    actions = {r["action"] for r in rows}
    assert {"create", "update", "status"} <= actions
    done = next(r for r in rows if r["action"] == "status" and (r["detail"] or {}).get("status") == "done" and (r["detail"] or {}).get("asset_hours") == "12510")
    assert done["detail"]["number"] == f"BK-{YEAR}-0004"
    assert any(r["action"] == "status" and (r["detail"] or {}).get("downtime_minutes") for r in rows)
    assert any(r["action"] == "create" and (r["detail"] or {}).get("name") == "Aylık genel kontrol" for r in rows)
