"""Sıfırdan bir makine ve parçalarını sisteme girme senaryosu (Faz 0 hedefi)."""

import pytest

from conftest import asset_id

TIRE = {"size": "23.5R25", "construction": "radial", "tra_code": "L-3", "otd_mm": 32, "scrap_tread_mm": 5}


@pytest.fixture(scope="module")
def loader_template(client, manager):
    return next(t for t in client.get("/catalog/templates", headers=manager).json() if t["layout"] == "loader")


def test_sablonlar_pozisyonlariyla_gelir(loader_template):
    assert loader_template["is_library"] is True
    assert {p["code"] for p in loader_template["positions"]} >= {"A1-L", "A2-R", "MAIN-PUMP"}


def test_uctan_uca_yeni_makine_ve_lastik(client, manager, tech, loader_template):
    # Saha
    site = client.post("/sites", headers=manager, json={"name": "Aliağa depo", "kind": "depo", "city": "İzmir"})
    assert site.status_code == 201, site.text

    # Makine modeli (ortak yükleyici şablonuyla)
    model = client.post("/catalog/asset-models", headers=manager, json={
        "manufacturer": "Caterpillar", "model": "966M", "category": "wheel_loader",
        "template_id": loader_template["id"]})
    assert model.status_code == 201, model.text

    # Makine: QR verilmedi, otomatik üretilmeli
    asset = client.post("/assets", headers=manager, json={
        "code": "LD-11", "model_id": model.json()["id"], "site_id": site.json()["id"],
        "serial_no": "CAT966M-0042", "year": 2023, "meter_hours": 2140})
    assert asset.status_code == 201, asset.text
    a = asset.json()
    assert a["qr_code"].startswith("ST-A-") and len(a["qr_code"]) == 15

    # Lastik katalog kalemi
    part = client.post("/catalog/parts", headers=manager, json={
        "category_code": "tire", "name": "23.5R25 L-3 radyal", "manufacturer": "Michelin",
        "part_no": "XHA2-23.5R25", "list_cost": 5200, "min_stock": 2, "tire": TIRE})
    assert part.status_code == 201, part.text

    # 4 lastik teslim alındı (teknisyen)
    recv = client.post("/parts", headers=tech, json={
        "part_id": part.json()["id"], "site_id": site.json()["id"],
        "items": [{"serial_no": f"MX23-{i}"} for i in range(1, 5)]})
    assert recv.status_code == 201, recv.text
    items = recv.json()
    assert len(items) == 4 and all(i["status"] == "in_stock" and i["qr_code"].startswith("ST-P-") for i in items)

    # Katalogda stok adedi görünür
    cat = {p["part_no"]: p for p in client.get("/catalog/parts", params={"category": "tire"}, headers=tech).json()}
    assert cat["XHA2-23.5R25"]["in_stock"] == 4

    # Takma
    for item, pos in zip(items, ["A1-L", "A1-R", "A2-L", "A2-R"]):
        r = client.post(f"/parts/{item['id']}/install", headers=tech, json={"asset_id": a["id"], "position": pos})
        assert r.status_code == 200, r.text

    detail = client.get(f"/assets/{a['id']}", headers=tech).json()
    tires = [p for p in detail["positions"] if p["category_code"] == "tire"]
    assert all(p["part_item_id"] for p in tires)
    assert all(p["band"] == "unknown" for p in tires)  # henüz ölçüm yok
    assert all(p["band"] == "empty" for p in detail["positions"] if p["category_code"] != "tire")

    # QR okutunca parça bulunur ve geçmişi var
    q = client.get(f"/qr/{items[0]['qr_code']}", headers=tech).json()
    assert q == {"type": "part", "id": items[0]["id"]}
    events = [e["event_type"] for e in client.get(f"/parts/{q['id']}/events", headers=tech).json()]
    assert events == ["installed", "received"]


def test_ayni_seri_numarasi_iki_kez_girilemez(client, tech, manager):
    part_id = next(p["id"] for p in client.get("/catalog/parts", headers=manager).json()
                   if p["part_no"] == "XHA2-23.5R25")
    r = client.post("/parts", headers=tech, json={"part_id": part_id, "items": [{"serial_no": "MX23-1"}]})
    assert r.status_code == 409
    r = client.post("/parts", headers=tech, json={"part_id": part_id, "items": [{"serial_no": "X"}, {"serial_no": "X"}]})
    assert r.status_code == 422


def test_lastik_kalemi_lastik_bilgisi_ister(client, manager):
    r = client.post("/catalog/parts", headers=manager, json={"category_code": "tire", "name": "Eksik lastik"})
    assert r.status_code == 422
    bad = {**TIRE, "scrap_tread_mm": 40}
    r = client.post("/catalog/parts", headers=manager, json={"category_code": "tire", "name": "X", "tire": bad})
    assert r.status_code == 422


def test_silindir_kalemi_omurle(client, manager):
    r = client.post("/catalog/parts", headers=manager, json={
        "category_code": "hyd_cylinder", "name": "966M kaldırma silindiri", "manufacturer": "Caterpillar",
        "part_no": "CAT-LIFT-966", "expected_life_hours": 14000})
    assert r.status_code == 201, r.text
    assert r.json()["specs"]["expected_life_hours"] == 14000


def test_teknisyen_makine_ve_katalog_tanimlayamaz(client, tech):
    assert client.post("/sites", headers=tech, json={"name": "Yetkisiz saha"}).status_code == 403
    assert client.post("/catalog/parts", headers=tech, json={
        "category_code": "filter", "name": "Yetkisiz"}).status_code == 403


def test_makine_guncelleme(client, manager):
    ld11 = asset_id(client, manager, "LD-11")
    r = client.patch(f"/assets/{ld11}", headers=manager, json={"status": "maintenance", "notes": "Fren bakımı"})
    assert r.status_code == 200
    assert r.json()["status"] == "maintenance"
    assert client.patch(f"/assets/{ld11}", headers=manager, json={}).status_code == 422


def test_baska_firma_demo_modeli_ve_sahasini_kullanamaz(client, manager, other):
    demo_model = client.get("/catalog/asset-models", headers=manager).json()[0]["id"]
    r = client.post("/assets", headers=other, json={"code": "X-1", "model_id": demo_model})
    assert r.status_code == 404
    demo_site = client.get("/sites", headers=manager).json()[0]["id"]
    templates = client.get("/catalog/templates", headers=other).json()
    m = client.post("/catalog/asset-models", headers=other, json={
        "manufacturer": "A", "model": "B", "category": "forklift", "template_id": templates[0]["id"]}).json()
    r = client.post("/assets", headers=other, json={"code": "X-1", "model_id": m["id"], "site_id": demo_site})
    assert r.status_code == 404


def test_qr_etiket_sayfasi(client, manager, other):
    ld11 = asset_id(client, manager, "LD-11")
    tires = [p["part_item_id"] for p in client.get(f"/assets/{ld11}", headers=manager).json()["positions"]
             if p["part_item_id"]]
    r = client.post("/labels", headers=manager, json={"asset_ids": [ld11], "part_ids": tires, "skip": 2})
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 5

    sheet = client.get(r.json()["url"].replace("http://testserver", ""))
    assert sheet.status_code == 200
    body = sheet.text
    assert body.count("<svg") == 5
    assert body.count('class="label empty"') == 2
    assert "LD-11" in body and "MX23-1" in body and "Caterpillar 966M" in body

    # Başka firma bu kayıtlar için etiket üretemez
    assert client.post("/labels", headers=other, json={"asset_ids": [ld11]}).status_code == 404
    assert client.get("/labels/sheet/sahte").status_code == 403
    assert client.post("/labels", headers=manager, json={}).status_code == 422
