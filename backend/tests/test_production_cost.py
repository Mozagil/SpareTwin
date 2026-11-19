"""Üretim maliyeti: malzeme + işçilik + makine saati; emir tamamlanınca hesaplanır, ürün stoğa birim maliyetle girer."""

import psycopg
import pytest

PRODUCT = "51111111-0000-0000-0000-000000000013"    # VOE-SK-LIFT220 (adetle izlenen kalem; burada ürün)
FILTER = "51111111-0000-0000-0000-000000000011"     # VOE-11110683 (sarf)
OIL = "51111111-0000-0000-0000-000000000012"        # RIMULA-R4-15W40 (sarf, litre)
SOMA = "21111111-0000-0000-0000-000000000002"       # stokların durduğu depo
URL = "/production"
# Kesim: makineli (60 $/saat); Montaj: elle
ROUTE = [{"name": "Kesim", "planned_minutes": 30, "machine_rate": 60}, {"name": "Montaj", "planned_minutes": 15}]
LABOR = 20


def work(client, settings, tech, oid: str, op: dict, minutes: int) -> None:
    """İşlemde `minutes` dakika çalışılmış gibi: başla, kaydı geriye çek, bitir."""
    assert client.post(f"{URL}/orders/{oid}/ops/{op['id']}/start", headers=tech).status_code == 200
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("update public.production_time_logs set started_at = now() - make_interval(mins => %s) "
                     "where op_id = %s and ended_at is null", [minutes, op["id"]])
        conn.commit()
    assert client.post(f"{URL}/orders/{oid}/ops/{op['id']}/stop", headers=tech, json={"done": True}).status_code == 200


def test_rota_makine_orani_ve_plan_maliyeti(client, manager, tech):
    r = client.patch("/organization", headers=manager, json={"thresholds": {"labor_cost_per_hour": LABOR}})
    assert r.status_code == 200 and r.json()["thresholds"]["labor_cost_per_hour"] == LABOR
    assert client.patch("/organization", headers=manager, json={"thresholds": {"labor_cost_per_hour": -1}}).status_code == 422

    bom = client.post(f"{URL}/boms", headers=manager, json={"part_id": PRODUCT}).json()["id"]
    for part, qty in ((FILTER, 1), (OIL, 2)):
        assert client.post(f"{URL}/boms/{bom}/lines", headers=manager, json={"part_id": part, "qty": qty}).status_code == 201
    bad = {"operations": [{"name": "Kesim", "machine_rate": -5}]}
    assert client.put(f"{URL}/routes/{bom}", headers=manager, json=bad).status_code == 422
    route = client.put(f"{URL}/routes/{bom}", headers=manager, json={"operations": ROUTE}).json()
    assert [(o["name"], o["machine_rate"] and float(o["machine_rate"])) for o in route] == [("Kesim", 60), ("Montaj", None)]

    o = client.post(f"{URL}/orders", headers=manager, json={"part_id": PRODUCT, "qty": 2}).json()
    assert [op["machine_rate"] and float(op["machine_rate"]) for op in o["operations"]] == [60, None]
    assert o["material_cost"] is None and o["total_cost"] is None and o["unit_cost"] is None
    # Plan: malzeme stok ortalama maliyetiyle; işçilik (60 + 30 dk) × 20; makine 60 dk × 60
    stock = {s["part_id"]: s for s in client.get("/stock", headers=tech).json()}
    material = 2 * float(stock[FILTER]["avg_cost"]) + 4 * float(stock[OIL]["avg_cost"])
    p = o["planned_cost"]
    assert material > 0 and float(p["material"]) == pytest.approx(material, abs=0.01)
    assert float(p["labor"]) == 30 and float(p["machine"]) == 60 and float(p["labor_rate"]) == LABOR
    assert float(p["total"]) == pytest.approx(material + 90, abs=0.01)
    assert float(p["unit"]) == pytest.approx((material + 90) / 2, abs=0.01)

    # Rota sonradan değişse de emrin makine oranı değişmez
    client.put(f"{URL}/routes/{bom}", headers=manager, json={"operations": [{**ROUTE[0], "machine_rate": 999}, ROUTE[1]]})
    assert float(client.get(f"{URL}/orders/{o['id']}", headers=tech).json()["operations"][0]["machine_rate"]) == 60


def test_tamamlaninca_maliyet_hesaplanir(client, settings, manager, tech):
    o = client.get(f"{URL}/orders", headers=tech).json()[0]
    oid = o["id"]
    kesim, montaj = client.get(f"{URL}/orders/{oid}", headers=tech).json()["operations"]
    work(client, settings, tech, oid, kesim, 90)      # plan 60 dk
    work(client, settings, tech, oid, montaj, 30)     # plan 30 dk

    r = client.post(f"{URL}/orders/{oid}/finish", headers=tech, json={
        "site_id": SOMA, "good_qty": 1, "scrap_qty": 1, "scrap_reason": "workmanship",
        "materials": [{"part_id": FILTER, "actual_qty": 3, "reason": "material"}]})
    assert r.status_code == 200, r.text
    d = r.json()
    material = sum(float(m["actual_qty"]) * float(m["unit_cost"]) for m in d["materials"])
    assert float(d["material_cost"]) == pytest.approx(material, abs=0.01)
    # İşçilik: (90 + 30) dk × 20 $/saat; makine: yalnızca Kesim, 90 dk × 60 $/saat
    assert float(d["labor_cost"]) == pytest.approx(40, abs=0.05) and float(d["labor_rate"]) == LABOR
    assert float(d["machine_cost"]) == pytest.approx(90, abs=0.05)
    total = float(d["total_cost"])
    assert total == pytest.approx(material + 130, abs=0.1)
    # Birim maliyet sağlam ürüne bölünür: hurdanın maliyeti sağlam ürüne biner
    assert float(d["unit_cost"]) == pytest.approx(total, abs=0.01)
    # Plan, gerçekleşenle aynı fiyatla: fark miktar ve süreden gelir
    assert float(d["planned_cost"]["labor"]) == 30 and float(d["planned_cost"]["machine"]) == 60
    assert float(d["planned_cost"]["material"]) < float(d["material_cost"])

    # Sağlam ürün stoğa üretim birim maliyetiyle girer
    mv = client.get(f"/stock/{PRODUCT}/movements", headers=tech).json()[0]
    assert mv["ref"] == d["number"] and float(mv["qty"]) == 1 and float(mv["unit_cost"]) == pytest.approx(total, abs=0.01)

    # Oran sonradan değişse de kapanmış emrin maliyeti değişmez
    client.patch("/organization", headers=manager, json={"thresholds": {"labor_cost_per_hour": 500}})
    again = client.get(f"{URL}/orders/{oid}", headers=tech).json()
    assert again["labor_cost"] == d["labor_cost"] and again["planned_cost"] == d["planned_cost"]


def test_maliyet_raporu(client, tech, other):
    rep = client.get(f"{URL}/reports/cost", headers=tech).json()
    assert rep["months"] == 12 and rep["labor_cost_per_hour"] == 500
    (p,) = rep["products"]
    assert p["part_id"] == PRODUCT and p["order_count"] == 1 and float(p["good_qty"]) == 1 and float(p["scrap_qty"]) == 1
    assert float(p["labor_cost"]) == pytest.approx(40, abs=0.05) and float(p["machine_cost"]) == pytest.approx(90, abs=0.05)
    assert float(p["total_cost"]) == pytest.approx(float(p["material_cost"]) + float(p["labor_cost"]) + float(p["machine_cost"]), abs=0.01)
    assert float(p["unit_cost"]) == pytest.approx(float(p["total_cost"]), abs=0.01)
    assert client.get(f"{URL}/reports/cost", headers=other).json()["products"] == []
