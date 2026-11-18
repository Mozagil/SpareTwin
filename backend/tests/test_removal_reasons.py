"""Sökme sebebi sabit listeden seçilir; sebep bazlı rapor sökme olaylarından hesaplanır."""

from conftest import part_id

TIRE_295 = "51111111-0000-0000-0000-000000000001"


def report(client, headers, **params):
    r = client.get("/reports/removal-reasons", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_sebep_bazinda_dagilim(client, manager):
    rep = report(client, manager)
    assert rep["months"] == 12 and rep["total"] == 15 and rep["rotations"] == 0
    reasons = {r["reason"]: r for r in rep["reasons"]}
    assert [r["reason"] for r in rep["reasons"]][:2] == ["worn_out", "cut"]  # en sık sebep önce
    assert reasons["worn_out"]["count"] == 6 and reasons["cut"]["count"] == 4 and reasons["impact"]["count"] == 2
    # Sökme anındaki ortalama çalışma saati: kesik, aşınmadan çok önce bitiriyor
    assert reasons["worn_out"]["avg_part_hours"] == round((6800 + 7100 + 6500 + 5200 + 4900 + 3900) / 6)
    assert reasons["cut"]["avg_part_hours"] == round((2100 + 3400 + 1800 + 2600) / 4)
    assert sum(r["count"] for r in rep["reasons"]) == rep["total"]


def test_kalem_ve_makine_bazinda(client, manager):
    rep = report(client, manager)
    tire = next(p for p in rep["by_part"] if p["part_id"] == TIRE_295)
    assert rep["by_part"][0]["part_id"] == TIRE_295  # en çok sökülen kalem önce
    assert tire["count"] == 8 and tire["reasons"] == {"worn_out": 3, "cut": 3, "impact": 1, "pressure_loss": 1}
    ld07 = next(a for a in rep["by_asset"] if a["code"] == "LD-07")
    assert ld07["count"] == 6 and ld07["reasons"]["cut"] == 3
    # Süzgeçler: parça tipi ve dönem
    tires = report(client, manager, category="tire")
    assert tires["total"] == 14 and all(p["category_code"] == "tire" for p in tires["by_part"])
    short = report(client, manager, months=3)
    assert short["total"] == 1 and [r["reason"] for r in short["reasons"]] == ["impact"]
    assert client.get("/reports/removal-reasons", headers=manager, params={"months": 0}).status_code == 422


def test_sebep_sabit_listeden_secilir(client, tech, manager):
    tire = part_id(client, tech, "MX29-0412")
    r = client.post(f"/parts/{tire}/remove", headers=tech, json={"reason": "yırtıldı"})
    assert r.status_code == 422 and any(f["field"] == "reason" for f in r.json()["fields"])
    r = client.post(f"/parts/{tire}/remove", headers=tech, json={"reason": "cut", "next_status": "scrapped"})
    assert r.status_code == 200, r.text
    rep = report(client, manager)
    assert rep["total"] == 16 and next(x for x in rep["reasons"] if x["reason"] == "cut")["count"] == 5


def test_rotasyon_sebep_sayilmaz(client, tech, manager):
    before = report(client, manager)
    a1r = part_id(client, tech, "MX29-0413")
    assert client.post(f"/parts/{a1r}/move", headers=tech, json={"position": "A2-L"}).status_code == 200
    after = report(client, manager)
    assert after["total"] == before["total"] and after["rotations"] == before["rotations"] + 2  # iki lastik yer değiştirdi
    assert "rotation" not in {r["reason"] for r in after["reasons"]}


def test_baska_firma_gormez(client, other):
    rep = report(client, other)
    assert rep["total"] == 0 and rep["reasons"] == [] and rep["by_part"] == []
