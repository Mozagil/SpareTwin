"""Satınalma: tedarikçi, ihtiyaç önerisi, talep → sipariş → teslim alma, iptal, bildirim, denetim."""

from datetime import date, timedelta

from conftest import asset_id

FILTER = "51111111-0000-0000-0000-000000000011"   # L220H hidrolik filtresi (adet, kritik 6, stokta 4, siparişte 10)
SEAL = "51111111-0000-0000-0000-000000000013"     # keçe takımı (stokta 1, kritik 2, siparişte 1)
TIRE = "51111111-0000-0000-0000-000000000001"     # 29.5R25 (seri numaralı, stokta 1, kritik 2)
VOLVO = "61111111-0000-0000-0000-000000000001"
SEED_PO = "71111111-0000-0000-0000-000000000001"
SOMA = "21111111-0000-0000-0000-000000000002"
YEAR = date.today().year


def stock_row(client, h, part):
    return next(s for s in client.get("/stock", headers=h).json() if s["part_id"] == part)


def test_tedarikci_listesi_ve_yetki(client, manager, tech):
    rows = client.get("/purchasing/suppliers", headers=manager).json()
    volvo = next(s for s in rows if s["id"] == VOLVO)
    assert volvo["open_orders"] == 1 and volvo["lead_time_days"] == 7
    body = {"name": "Hidrolik Market", "phone": "0232 000", "lead_time_days": 3}
    assert client.post("/purchasing/suppliers", headers=tech, json=body).status_code == 403
    r = client.post("/purchasing/suppliers", headers=manager, json=body)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert client.post("/purchasing/suppliers", headers=manager, json=body).status_code in (409, 422)  # aynı ad
    r = client.patch(f"/purchasing/suppliers/{sid}", headers=manager, json={**body, "is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    ids = {s["id"] for s in client.get("/purchasing/suppliers", headers=manager).json()}
    assert sid not in ids
    ids = {s["id"] for s in client.get("/purchasing/suppliers", headers=manager, params={"include_inactive": True}).json()}
    assert sid in ids


def test_ihtiyac_onerisi_ve_bildirim(client, manager):
    needs = {n["part_id"]: n for n in client.get("/purchasing/needs", headers=manager).json()}
    tire = needs[TIRE]
    # LD-07 A2-L %13 ile kritik → en az 1 yaklaşan değişim; stokta 1, kritik seviye 2, siparişte 0
    assert tire["upcoming"] >= 1 and float(tire["in_stock"]) == 1 and float(tire["on_order"]) == 0
    assert float(tire["need"]) == tire["upcoming"] + 2 - 1
    assert "LD-07" in {i["asset_code"] for i in tire["items"]}
    assert all(i["band"] == "critical" or (i["hours_left"] is not None and i["hours_left"] <= 500) for i in tire["items"])
    # Filtre kritik altında (4 < 6) ama siparişte 10 var → ihtiyaç listesinde değil
    assert FILTER not in needs
    # Keçe takımı: 1 + siparişte 1 = 2 = kritik seviye → ihtiyaç yok
    assert SEAL not in needs

    items = client.get("/notifications", headers=manager).json()["items"]
    need = [n for n in items if n["kind"] == "purchase_need" and n["link"]["id"] == TIRE]
    assert len(need) == 1
    assert need[0]["title"].startswith("LD-07") and "lastik yaklaşıyor, stokta 1 var" in need[0]["title"]
    assert need[0]["link"]["type"] == "purchasing" and "önerilen sipariş" in need[0]["body"]
    low = next(n for n in items if n["kind"] == "stock_low" and n["link"]["id"] == FILTER)
    assert "siparişte 10 adet" in low["body"]


def test_talep_siparis_teslim_akisi(client, manager, tech):
    ld07 = asset_id(client, tech, "LD-07")
    lines = [{"part_id": FILTER, "qty": 5, "unit_cost": 83},
             {"part_id": TIRE, "qty": 2, "unit_cost": 9500, "asset_id": ld07, "notes": "A2-L ve A2-R için"}]
    bad = client.post("/purchasing/orders", headers=tech, json={"lines": [lines[0], lines[0]]})
    assert bad.status_code == 422
    r = client.post("/purchasing/orders", headers=tech, json={"site_id": SOMA, "lines": lines, "notes": "Soma bakım"})
    assert r.status_code == 201, r.text
    o = r.json()
    oid = o["id"]
    assert o["status"] == "draft" and o["number"] == f"SA-{YEAR}-0002" and o["line_count"] == 2
    assert float(o["total"]) == 5 * 83 + 2 * 9500 and o["requested_by_name"] == "Demo Teknisyen"
    tire_line = next(ln for ln in o["lines"] if ln["part_id"] == TIRE)
    filter_line = next(ln for ln in o["lines"] if ln["part_id"] == FILTER)
    assert tire_line["is_serialized"] and tire_line["asset_code"] == "LD-07"

    # Talep listede, ihtiyaçta "talepte" olarak görünür
    assert any(x["id"] == oid for x in client.get("/purchasing/orders", headers=tech, params={"open_only": True}).json())
    need = next(n for n in client.get("/purchasing/needs", headers=tech).json() if n["part_id"] == TIRE)
    assert float(need["requested"]) == 2

    # Sipariş vermek yönetici işi; tedarikçi şart
    assert client.post(f"/purchasing/orders/{oid}/status", headers=tech, json={"status": "ordered"}).status_code == 403
    r = client.post(f"/purchasing/orders/{oid}/status", headers=manager, json={"status": "ordered"})
    assert r.status_code == 422 and "tedarikçi" in r.json()["detail"]
    r = client.patch(f"/purchasing/orders/{oid}", headers=tech, json={"supplier_id": VOLVO, "expected_at": str(date.today() + timedelta(days=7))})
    assert r.status_code == 200 and r.json()["supplier_name"] == "Volvo Yetkili Servis"
    r = client.post(f"/purchasing/orders/{oid}/status", headers=manager, json={"status": "ordered"})
    assert r.status_code == 200 and r.json()["status"] == "ordered" and r.json()["ordered_by_name"] == "Demo Yönetici"
    r = client.patch(f"/purchasing/orders/{oid}", headers=tech, json={"lines": lines})
    assert r.status_code == 422 and "kalemler değiştirilemez" in r.json()["detail"]
    need = next(n for n in client.get("/purchasing/needs", headers=tech).json() if n["part_id"] == TIRE)
    assert float(need["on_order"]) == 2 and float(need["requested"]) == 0

    # Kısmi teslim: 3 filtre → stok defterine sipariş numarasıyla girer
    before = float(stock_row(client, tech, FILTER)["qty"])
    r = client.post(f"/purchasing/orders/{oid}/receive", headers=tech,
                    json={"ref": "IRS-9", "lines": [{"line_id": filter_line["id"], "qty": 3}]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "partial"
    assert float(next(ln for ln in r.json()["lines"] if ln["id"] == filter_line["id"])["received_qty"]) == 3
    assert float(stock_row(client, tech, FILTER)["qty"]) == before + 3
    mv = client.get(f"/stock/{FILTER}/movements", headers=tech).json()[0]
    assert mv["kind"] == "in" and float(mv["qty"]) == 3 and float(mv["unit_cost"]) == 83 and mv["ref"] == f"SA-{YEAR}-0002 / IRS-9"
    assert mv["site_name"] == "Soma açık ocak"
    r = client.post(f"/purchasing/orders/{oid}/receive", headers=tech, json={"lines": [{"line_id": filter_line["id"], "qty": 3}]})
    assert r.status_code == 422 and "kalan 2 adet" in r.json()["detail"]

    # Seri numaralı lastik: her adet için satır gerekir, parça kalemi olarak stoğa girer
    r = client.post(f"/purchasing/orders/{oid}/receive", headers=tech, json={"lines": [{"line_id": tire_line["id"], "qty": 2}]})
    assert r.status_code == 422 and "her adet için" in r.json()["detail"]
    r = client.post(f"/purchasing/orders/{oid}/receive", headers=tech, json={
        "lines": [{"line_id": tire_line["id"], "qty": 2, "serials": [{"serial_no": "MX29-9001"}, {"serial_no": "MX29-9002", "qr_code": "ST-P-TEST9002"}]}]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "partial"  # 2 filtre hâlâ bekliyor
    receipt = next(x for x in r.json()["receipts"] if x["line_id"] == tire_line["id"])
    assert {s["serial_no"] for s in receipt["serials"]} == {"MX29-9001", "MX29-9002"}
    new = [p for p in client.get("/parts", headers=tech, params={"q": "MX29-900"}).json() if p["serial_no"] in ("MX29-9001", "MX29-9002")]
    assert len(new) == 2 and all(p["status"] == "in_stock" for p in new)
    detail = client.get(f"/parts/{new[0]['id']}", headers=tech).json()
    assert float(detail["cost_total"]) == 9500 and any(e["event_type"] == "received" for e in client.get(f"/parts/{new[0]['id']}/events", headers=tech).json())
    assert float(stock_row(client, tech, TIRE)["qty"]) == 3

    # Kısmi teslimat iptal edilemez; kalanı kapatılır
    r = client.post(f"/purchasing/orders/{oid}/status", headers=manager, json={"status": "cancelled"})
    assert r.status_code == 422
    r = client.post(f"/purchasing/orders/{oid}/status", headers=manager, json={"status": "received"})
    assert r.status_code == 200 and r.json()["status"] == "received" and r.json()["closed_at"]
    r = client.post(f"/purchasing/orders/{oid}/receive", headers=tech, json={"lines": [{"line_id": filter_line["id"], "qty": 1}]})
    assert r.status_code == 422 and "teslim alınabilir durumda değil" in r.json()["detail"]
    assert client.patch(f"/purchasing/orders/{oid}", headers=tech, json={"notes": "x"}).status_code == 422
    assert not any(x["id"] == oid for x in client.get("/purchasing/orders", headers=tech, params={"open_only": True}).json())


def test_iptal_ve_izolasyon(client, manager, tech, other):
    r = client.post("/purchasing/orders", headers=tech, json={"lines": [{"part_id": SEAL, "qty": 1}]})
    assert r.status_code == 201
    oid = r.json()["id"]
    assert client.get(f"/purchasing/orders/{oid}", headers=other).status_code == 404
    assert client.patch(f"/purchasing/orders/{oid}", headers=other, json={"notes": "x"}).status_code == 404
    assert client.post(f"/purchasing/orders/{oid}/status", headers=other, json={"status": "cancelled"}).status_code == 404
    assert client.get("/purchasing/orders", headers=other).json() == []
    assert client.get("/purchasing/suppliers", headers=other).json() == []
    # Başka firmanın tedarikçisi / deposu kullanılamaz
    assert client.post("/purchasing/orders", headers=other, json={"supplier_id": VOLVO, "lines": [{"part_id": SEAL, "qty": 1}]}).status_code == 404
    r = client.post(f"/purchasing/orders/{oid}/status", headers=manager, json={"status": "cancelled"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert client.post(f"/purchasing/orders/{oid}/status", headers=manager, json={"status": "ordered"}).status_code == 422
    # Seri numaralı kalem tam adet; sipariş ver sonra 1,5 adet teslim denemesi
    r = client.post("/purchasing/orders", headers=manager, json={"supplier_id": VOLVO, "lines": [{"part_id": TIRE, "qty": 2}]})
    oid2 = r.json()["id"]
    client.post(f"/purchasing/orders/{oid2}/status", headers=manager, json={"status": "ordered"})
    line = r.json()["lines"][0]["id"]
    r = client.post(f"/purchasing/orders/{oid2}/receive", headers=tech, json={"lines": [{"line_id": line, "qty": 1.5}]})
    assert r.status_code == 422 and "tam adet" in r.json()["detail"]
    assert client.post(f"/purchasing/orders/{oid2}/status", headers=manager, json={"status": "cancelled"}).status_code == 200


def test_geciken_siparis_bildirimi(client, manager):
    yesterday = str(date.today() - timedelta(days=1))
    r = client.post("/purchasing/orders", headers=manager,
                    json={"supplier_id": VOLVO, "expected_at": yesterday, "lines": [{"part_id": SEAL, "qty": 2}]})
    oid, number = r.json()["id"], r.json()["number"]
    assert client.post(f"/purchasing/orders/{oid}/status", headers=manager, json={"status": "ordered"}).status_code == 200
    listed = next(x for x in client.get("/purchasing/orders", headers=manager).json() if x["id"] == oid)
    assert listed["late"] is True
    late = [n for n in client.get("/notifications", headers=manager).json()["items"] if n["kind"] == "po_late"]
    assert len(late) == 1 and late[0]["title"] == f"{number} teslimatı gecikti" and "1 gün gecikme" in late[0]["body"]
    assert late[0]["link"] == {"type": "order", "id": oid}
    client.post(f"/purchasing/orders/{oid}/status", headers=manager, json={"status": "cancelled"})
    assert not [n for n in client.get("/notifications", headers=manager).json()["items"] if n["kind"] == "po_late"]


def test_denetim_kaydi(client, manager):
    rows = [r for r in client.get("/audit", headers=manager, params={"limit": 500}).json() if r["entity_type"] == "purchasing"]
    actions = {r["action"] for r in rows}
    assert {"create", "update", "status", "receive"} <= actions
    rec = next(r for r in rows if r["action"] == "receive" and r["status"] == 200 and r["detail"]["ref"] == "IRS-9")
    assert rec["detail"]["number"] == f"SA-{YEAR}-0002" and rec["detail"]["received"][0]["qty"] == "3"
    assert any(r["action"] == "status" and r["detail"].get("status") == "ordered" for r in rows)
