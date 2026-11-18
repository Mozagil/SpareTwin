"""Emrin stokla bağı, fire ve hurda: malzeme emre kopyalanır, tamamlanınca stok hareket eder, rapor."""

PRODUCT = "51111111-0000-0000-0000-000000000013"    # VOE-SK-LIFT220 (adetle izlenen kalem; burada ürün)
FILTER = "51111111-0000-0000-0000-000000000011"     # VOE-11110683 (sarf)
OIL = "51111111-0000-0000-0000-000000000012"        # RIMULA-R4-15W40 (sarf, litre)
SERIAL = "51111111-0000-0000-0000-000000000005"     # VOE-LIFT-220 (seri numarasıyla izlenir)
SOMA = "21111111-0000-0000-0000-000000000002"       # stokların durduğu depo
URL = "/production"


def stock(client, headers) -> dict:
    return {r["part_id"]: float(r["qty"]) for r in client.get("/stock", headers=headers).json()}


def mats(order: dict) -> dict:
    return {m["part_id"]: m for m in order["materials"]}


def test_malzeme_emre_kopyalanir(client, manager, tech):
    bom = client.post(f"{URL}/boms", headers=manager, json={"part_id": PRODUCT}).json()["id"]
    for part, qty in ((FILTER, 1), (OIL, "2.5"), (SERIAL, 1)):
        assert client.post(f"{URL}/boms/{bom}/lines", headers=manager, json={"part_id": part, "qty": qty}).status_code == 201
    client.put(f"{URL}/routes/{bom}", headers=manager, json={"operations": [{"name": "Montaj", "planned_minutes": 10}]})
    r = client.post(f"{URL}/orders", headers=manager, json={"part_id": PRODUCT, "qty": 2})
    assert r.status_code == 201, r.text
    o = r.json()
    m = mats(o)
    assert {k: float(v["planned_qty"]) for k, v in m.items()} == {FILTER: 2, OIL: 5, SERIAL: 2}
    assert all(v["actual_qty"] is None for v in m.values()) and m[SERIAL]["is_serialized"] and not m[OIL]["is_serialized"]
    assert o["good_qty"] is None and o["scrap_qty"] is None

    # Ağaç sonradan değişse de açılmış emrin malzeme planı değişmez
    line = next(x["line_id"] for x in client.get(f"{URL}/boms/{bom}", headers=manager).json()["lines"] if x["part_id"] == OIL)
    assert client.delete(f"{URL}/boms/{bom}/lines/{line}", headers=manager).status_code == 204
    assert float(mats(client.get(f"{URL}/orders/{o['id']}", headers=tech).json())[OIL]["planned_qty"]) == 5


def test_tamamlama_stoku_isler(client, manager, tech, other):
    o = client.get(f"{URL}/orders", headers=tech).json()[0]
    oid = o["id"]
    op = client.get(f"{URL}/orders/{oid}", headers=tech).json()["operations"][0]["id"]
    finish = lambda h, **body: client.post(f"{URL}/orders/{oid}/finish", headers=h, json=body)  # noqa: E731

    # İşlem bitmeden tamamlanmaz
    assert finish(tech, good_qty=2, site_id=SOMA).status_code == 422
    assert client.post(f"{URL}/orders/{oid}/ops/{op}/stop", headers=tech, json={"done": True}).status_code == 200
    assert finish(other, good_qty=2, site_id=SOMA).status_code == 404
    assert finish(tech, good_qty=0, site_id=SOMA).status_code == 422
    # Hurda ve plandan fazla malzeme sebep ister
    r = finish(tech, good_qty=1, scrap_qty=1, site_id=SOMA)
    assert r.status_code == 422 and "sebep" in r.json()["detail"]
    r = finish(tech, good_qty=2, site_id=SOMA, materials=[{"part_id": FILTER, "actual_qty": 3}])
    assert r.status_code == 422 and "sebep" in r.json()["detail"]
    assert finish(tech, good_qty=2, scrap_qty=1, scrap_reason="yanlis", site_id=SOMA).status_code == 422
    # Stok seçilen depoda aranır: depo belirtilmezse yetmez; yetmeyen kalem adıyla söylenir
    before = stock(client, tech)
    r = finish(tech, good_qty=2)
    assert r.status_code == 422 and "stok yetmiyor" in r.json()["detail"]
    r = finish(tech, good_qty=2, site_id=SOMA, materials=[{"part_id": FILTER, "actual_qty": 500, "reason": "other"}])
    assert r.status_code == 422 and "stok yetmiyor" in r.json()["detail"]
    # Başarısız deneme hiçbir şey değiştirmez
    assert stock(client, tech) == before
    assert client.get(f"{URL}/orders/{oid}", headers=tech).json()["status"] == "in_progress"

    r = finish(tech, good_qty=1, scrap_qty=1, scrap_reason="workmanship", site_id=SOMA, materials=[
        {"part_id": FILTER, "actual_qty": 3, "reason": "material"},
        {"part_id": OIL, "actual_qty": "4.5", "reason": "other"}])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "done" and float(d["good_qty"]) == 1 and float(d["scrap_qty"]) == 1
    assert d["scrap_reason"] == "workmanship" and d["site_id"] == SOMA and d["site_name"]
    m = mats(d)
    assert float(m[FILTER]["actual_qty"]) == 3 and m[FILTER]["reason"] == "material" and m[FILTER]["stock_moved"]
    assert float(m[FILTER]["unit_cost"]) > 0
    # Plandan az kullanımda sebep tutulmaz; listede olmayan malzeme planlandığı kadar sayılır
    assert float(m[OIL]["actual_qty"]) == 4.5 and m[OIL]["reason"] is None
    # Seri numaralı kalem: kayıt var, stok hareketi yok
    assert float(m[SERIAL]["actual_qty"]) == 2 and not m[SERIAL]["stock_moved"]

    after = stock(client, tech)
    assert after[FILTER] == before[FILTER] - 3 and after[OIL] == before[OIL] - 4.5
    assert after[PRODUCT] == before[PRODUCT] + 1          # yalnızca sağlam ürün stoğa girer
    assert after[SERIAL] == before[SERIAL]
    moves = client.get(f"/stock/{FILTER}/movements", headers=tech).json()
    assert moves[0]["ref"] == d["number"] and moves[0]["reason"] == "üretim" and float(moves[0]["qty"]) == -3

    assert finish(tech, good_qty=1, site_id=SOMA).status_code == 422
    assert client.post(f"{URL}/orders/{oid}/status", headers=manager, json={"status": "cancelled"}).status_code == 422


def test_fire_hurda_raporu(client, manager, tech, other):
    rep = client.get(f"{URL}/reports/scrap", headers=tech).json()
    p = next(x for x in rep["products"] if x["part_id"] == PRODUCT)
    assert p["order_count"] == 1 and float(p["planned_qty"]) == 2 and float(p["good_qty"]) == 1 and float(p["scrap_qty"]) == 1
    m = {x["part_id"]: x for x in rep["materials"]}
    assert float(m[FILTER]["planned_qty"]) == 2 and float(m[FILTER]["actual_qty"]) == 3 and float(m[FILTER]["waste_cost"]) > 0
    assert float(m[OIL]["actual_qty"]) == 4.5 and float(m[OIL]["waste_cost"]) < 0      # tasarruf
    r = {x["reason"]: x for x in rep["reasons"]}
    assert set(r) == {"workmanship", "material"}
    assert r["workmanship"]["scrap_orders"] == 1 and r["workmanship"]["waste_lines"] == 0
    assert r["material"]["waste_lines"] == 1 and float(r["material"]["waste_cost"]) == float(m[FILTER]["waste_cost"])
    assert client.get(f"{URL}/reports/scrap", headers=other).json() == {"months": 12, "products": [], "materials": [], "reasons": []}
