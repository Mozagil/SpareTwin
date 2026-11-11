"""Maliyet raporu (TCO): parça + sarf + işçilik + dış servis + duruş, dönem, saha süzgeci, duruş saat maliyeti (firma ve makine), izolasyon, Excel / PDF çıktısı."""

import io
from datetime import datetime, timedelta, timezone

import pypdf
from openpyxl import load_workbook

LD07 = "41111111-0000-0000-0000-000000000001"
LD09 = "41111111-0000-0000-0000-000000000002"
RS02 = "41111111-0000-0000-0000-000000000003"
FL14 = "41111111-0000-0000-0000-000000000004"
AMBARLI = "21111111-0000-0000-0000-000000000001"
OIL = "51111111-0000-0000-0000-000000000012"
COSTS = ("parts_cost", "consumables_cost", "labor_cost", "external_cost", "downtime_cost")


def tco(client, h, **params):
    r = client.get("/reports/tco", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def row(rep, asset):
    return {k: (float(v) if k in (*COSTS, "total", "hours_worked", "cost_per_hour") and v is not None else v)
            for k, v in next(a for a in rep["assets"] if a["asset_id"] == asset).items()}


def test_son_12_ay(client, tech):
    rep = tco(client, tech)
    assert rep["months"] == 12 and rep["currency"] == "USD" and rep["downtime_cost_per_hour"] == 150
    assert [a["asset_code"] for a in rep["assets"]] == ["LD-07", "LD-09", "RS-02", "FL-14"]  # pahalıdan ucuza

    ld07 = row(rep, LD07)
    # 4 lastik + 4 jant + 2 kaldırma silindiri + devirme silindiri + pompa, ilk takıldıkları makineye
    assert ld07["parts_cost"] == 4 * 9800 + 4 * 2600 + 2 * 4500 + 3900 + 6100
    assert ld07["consumables_cost"] == 4 * 82 + 60 * 4.05 + 340    # stok defterinden makineye çıkışlar
    assert ld07["labor_cost"] == 250 and ld07["external_cost"] == 0 and ld07["downtime_cost"] == 0
    assert ld07["total"] == sum(ld07[k] for k in COSTS) == 69761
    assert ld07["planned_done"] == 1 and ld07["breakdowns"] == 0 and ld07["model_name"] == "Volvo L220H"
    # Bir yıl önceki sayaç 9.600, bugün 12.480
    assert 2800 < ld07["hours_worked"] <= 2880 and ld07["cost_per_hour"] == round(ld07["total"] / ld07["hours_worked"], 2)

    # Tamir maliyeti (650) parçanın takılı olduğu makineye yazılır
    rs = row(rep, RS02)
    assert rs["parts_cost"] == 6 * 3200 + 8700 + 650 and rs["consumables_cost"] == 172

    # Arıza: 5 saat duruş × 150
    fl = row(rep, FL14)
    assert fl["downtime_minutes"] == 300 and fl["downtime_cost"] == 750 and fl["breakdowns"] == 1 and fl["labor_cost"] == 180
    assert fl["total"] == 8980 + 180 + 750

    t = rep["totals"]
    for k in (*COSTS, "total"):
        assert float(t[k]) == sum(float(a[k]) for a in rep["assets"])
    assert t["downtime_minutes"] == 300
    assert float(t["cost_per_hour"]) == round(float(t["total"]) / float(t["hours_worked"]), 2)


def test_donem_ve_saha(client, tech):
    rep = tco(client, tech, months=2)
    ld07 = row(rep, LD07)
    # Parçalar 200 gün önce takıldı: dönem dışı. Bakım (60 gün önce) ve keçe takımı (35 gün önce) dönemde.
    assert ld07["parts_cost"] == 0 and ld07["consumables_cost"] == 911 and ld07["labor_cost"] == 250 and ld07["total"] == 1161
    assert 620 < ld07["hours_worked"] < 650     # dönem başındaki saat iki okuma arasından bulunur
    assert row(rep, RS02)["parts_cost"] == 650  # yalnızca tamir

    amb = tco(client, tech, site_id=AMBARLI)
    assert {a["asset_code"] for a in amb["assets"]} == {"RS-02", "FL-14"}
    assert float(amb["totals"]["total"]) == row(amb, RS02)["total"] + row(amb, FL14)["total"]
    assert client.get("/reports/tco", headers=tech, params={"months": 0}).status_code == 422
    assert client.get("/reports/tco", headers=tech, params={"months": 61}).status_code == 422


def test_suren_ariza_ve_emir_sarfi(client, manager, tech):
    before = row(tco(client, tech), FL14)
    down_from = datetime.now(timezone.utc) - timedelta(hours=4)
    r = client.post("/maintenance/work-orders", headers=tech, json={
        "asset_id": FL14, "kind": "breakdown", "title": "Hidrolik hortum patladı", "reason_code": "hydraulic",
        "down_from": down_from.isoformat(), "parts": [{"part_id": OIL, "qty": 20, "site_id": AMBARLI}]})
    assert r.status_code == 201, r.text
    wid = r.json()["id"]
    # Süren arıza bugüne kadar sayılır; sarf henüz stoktan düşmedi
    mid = row(tco(client, tech), FL14)
    assert 300 + 239 <= mid["downtime_minutes"] <= 300 + 242 and mid["breakdowns"] == 2
    assert mid["downtime_cost"] == round(mid["downtime_minutes"] / 60 * 150, 2) and mid["consumables_cost"] == before["consumables_cost"]

    r = client.post(f"/maintenance/work-orders/{wid}/status", headers=tech,
                    json={"status": "done", "down_to": (down_from + timedelta(hours=3)).isoformat(), "labor_cost": 90, "external_cost": 450})
    assert r.status_code == 200, r.text
    after = row(tco(client, tech), FL14)
    assert after["downtime_minutes"] == 300 + 180 and after["downtime_cost"] == 8 * 150
    # Emrin sarfı stok defterinden, bir kez: 20 litre × ağırlıklı ortalama (400 × 4,05 + 120 × 4,30) / 520
    assert after["consumables_cost"] == before["consumables_cost"] + 82.15
    assert after["labor_cost"] == before["labor_cost"] + 90 and after["external_cost"] == 450
    assert after["total"] == before["total"] + 82.15 + 90 + 450 + 3 * 150

    # İptal edilen arıza emri duruş saymaz
    r = client.post("/maintenance/work-orders", headers=tech, json={
        "asset_id": FL14, "kind": "breakdown", "title": "Yanlış alarm", "down_from": down_from.isoformat()})
    client.post(f"/maintenance/work-orders/{r.json()['id']}/status", headers=manager, json={"status": "cancelled"})
    assert row(tco(client, tech), FL14)["downtime_minutes"] == 480


def test_durus_saat_maliyeti_ve_izolasyon(client, manager, other):
    r = client.patch("/organization", headers=manager, json={"thresholds": {"downtime_cost_per_hour": 0}})
    assert r.status_code == 200, r.text
    rep = tco(client, manager)
    fl = row(rep, FL14)
    assert rep["downtime_cost_per_hour"] == 0 and fl["downtime_cost"] == 0 and fl["downtime_minutes"] == 480
    assert client.patch("/organization", headers=manager, json={"thresholds": {"downtime_cost_per_hour": -1}}).status_code == 422
    client.patch("/organization", headers=manager, json={"thresholds": {"downtime_cost_per_hour": 200}})
    assert row(tco(client, manager), FL14)["downtime_cost"] == 8 * 200

    o = tco(client, other)
    assert [a["asset_code"] for a in o["assets"]] == ["BF-01"] and float(o["totals"]["total"]) == 0
    assert o["assets"][0]["cost_per_hour"] is None and o["downtime_cost_per_hour"] == 0


def test_makine_durus_orani(client, manager, tech):
    # Önceki testten: firma oranı 200, FL-14'te 8 saat duruş
    r = client.patch(f"/assets/{FL14}", headers=manager, json={"downtime_cost_per_hour": 400})
    assert r.status_code == 200, r.text
    assert float(r.json()["downtime_cost_per_hour"]) == 400
    rep = tco(client, tech)
    fl, ld = row(rep, FL14), row(rep, LD07)
    assert rep["downtime_cost_per_hour"] == 200          # firma oranı yerinde
    assert fl["downtime_cost"] == 8 * 400 and fl["downtime_rate_own"] is True and float(fl["downtime_rate"]) == 400
    assert ld["downtime_rate_own"] is False and float(ld["downtime_rate"]) == 200
    assert fl["total"] == sum(fl[k] for k in COSTS)

    # 0 da bir orandır: bu makinenin duruşu maliyet yazmaz
    client.patch(f"/assets/{FL14}", headers=manager, json={"downtime_cost_per_hour": 0})
    fl = row(tco(client, tech), FL14)
    assert fl["downtime_cost"] == 0 and fl["downtime_rate_own"] is True and fl["downtime_minutes"] == 480

    assert client.patch(f"/assets/{FL14}", headers=tech, json={"downtime_cost_per_hour": 10}).status_code == 403
    for bad in (-1, 100001):
        assert client.patch(f"/assets/{FL14}", headers=manager, json={"downtime_cost_per_hour": bad}).status_code == 422

    # Boşaltılınca firma oranına döner
    r = client.patch(f"/assets/{FL14}", headers=manager, json={"downtime_cost_per_hour": None})
    assert r.status_code == 200 and r.json()["downtime_cost_per_hour"] is None
    fl = row(tco(client, tech), FL14)
    assert fl["downtime_cost"] == 8 * 200 and fl["downtime_rate_own"] is False


def test_excel_ve_pdf(client, manager, tech, other):
    client.patch(f"/assets/{FL14}", headers=manager, json={"downtime_cost_per_hour": 400})
    rep = tco(client, tech)

    r = client.get("/reports/tco.xlsx", headers=tech)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="sparetwin-maliyet-12ay-' in r.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws["A1"].value.endswith("Makine toplam sahip olma maliyeti")
    lines = list(ws.iter_rows(min_row=4, values_only=True))
    head = list(lines[0])
    data = {x[0]: dict(zip(head, x)) for x in lines[1:]}
    assert list(data) == ["LD-07", "LD-09", "RS-02", "FL-14", "Filo"]
    assert data["LD-07"]["Toplam"] == row(rep, LD07)["total"] and data["LD-07"]["Parça"] == row(rep, LD07)["parts_cost"]
    assert data["FL-14"]["Duruş (saat)"] == 8 and data["FL-14"]["Duruş saat maliyeti"] == 400 and data["FL-14"]["Duruş maliyeti"] == 3200
    assert data["FL-14"]["Durum"] == "Aktif" and data["LD-07"]["Duruş saat maliyeti"] == 200
    assert data["Filo"]["Toplam"] == float(rep["totals"]["total"]) and data["Filo"]["Arıza"] == 2

    amb = list(load_workbook(io.BytesIO(
        client.get("/reports/tco.xlsx", headers=tech, params={"site_id": AMBARLI, "months": 24}).content)).active.iter_rows(min_row=5, values_only=True))
    assert {x[0] for x in amb} == {"RS-02", "FL-14", "Filo"}

    r = client.get("/reports/tco.pdf", headers=tech)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:5] == b"%PDF-"
    assert 'filename="sparetwin-maliyet-12ay-' in r.headers["content-disposition"]
    text = " ".join("\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(r.content)).pages).split())  # satır kırılmaları
    for s in ("Makine toplam sahip olma maliyeti", "LD-07", "FL-14", "Filo", "$400/saat", "FL-14 kendi oranıyla"):
        assert s in text, s

    # Başka firma: kendi makinesi, bizim verimiz yok
    text = "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(client.get("/reports/tco.pdf", headers=other).content)).pages)
    assert "LD-07" not in text and "Bu dönemde makinelere yazılmış maliyet yok" in text
    assert [x[0] for x in load_workbook(io.BytesIO(client.get("/reports/tco.xlsx", headers=other).content)).active.iter_rows(
        min_row=5, values_only=True)] == ["BF-01", "Filo"]
    assert client.get("/reports/tco.xlsx", headers=tech, params={"months": 0}).status_code == 422
    assert client.get("/reports/tco.pdf", headers=tech, params={"months": 61}).status_code == 422
    client.patch(f"/assets/{FL14}", headers=manager, json={"downtime_cost_per_hour": None})
