"""Firma kütüphanesi: kendi parça tipi (ölçüm profiliyle) ve kendi pozisyon şablonu."""

import pytest

GEARBOX = {
    "code": "gearbox", "name": "Şanzıman", "is_serialized": True,
    "measurement_profile": [
        {"metric": "oil_temp_c", "label": "Yağ sıcaklığı", "unit": "°C", "required": True, "min": 0, "max": 150},
        {"metric": "backlash_mm", "label": "Boşluk", "unit": "mm"},
    ],
    "required_photo_angles": ["overall"],
}
POSITIONS = [
    {"code": "A1-L", "label": "Ön sol", "category_code": "tire", "axle": 1, "x": 20, "y": 25},
    {"code": "A1-R", "label": "Ön sağ", "category_code": "tire", "axle": 1, "x": 20, "y": 75},
    {"code": "A1-L-J", "label": "Ön sol jantı", "category_code": "rim", "axle": 1},
    {"code": "GEARBOX", "label": "Şanzıman", "category_code": "gearbox", "x": 55, "y": 50},
]


@pytest.fixture(scope="module")
def gearbox(client, manager):
    r = client.post("/catalog/categories", headers=manager, json=GEARBOX)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def template(client, manager, gearbox):
    r = client.post("/catalog/templates", headers=manager,
                    json={"name": "Kırıcı (2 lastik + şanzıman)", "layout": "generic", "positions": POSITIONS})
    assert r.status_code == 201, r.text
    return r.json()


def test_parca_tipi_olusur_ve_listede_gorunur(client, manager, tech, other, gearbox):
    assert gearbox["is_library"] is False and gearbox["part_count"] == 0
    assert [m["metric"] for m in gearbox["measurement_profile"]] == ["oil_temp_c", "backlash_mm"]
    assert "min" not in gearbox["measurement_profile"][1]  # boş sınır yazılmaz

    cats = {c["code"]: c for c in client.get("/catalog/categories", headers=tech).json()}
    assert cats["gearbox"]["name"] == "Şanzıman" and cats["tire"]["is_library"] is True
    # Başka firma göremez
    assert "gearbox" not in {c["code"] for c in client.get("/catalog/categories", headers=other).json()}


def test_parca_tipi_kurallari(client, manager, tech, other, gearbox):
    # Yetki
    assert client.post("/catalog/categories", headers=tech, json={**GEARBOX, "code": "chain"}).status_code == 403
    # Ortak kütüphanedeki ya da firmadaki kod yeniden alınamaz
    assert client.post("/catalog/categories", headers=manager, json={**GEARBOX, "code": "tire"}).status_code == 409
    assert client.post("/catalog/categories", headers=manager, json=GEARBOX).status_code == 409
    # Geçersiz profil
    bad = {**GEARBOX, "code": "chain", "measurement_profile": [{"metric": "a_b", "label": "X", "min": 5, "max": 1}]}
    assert client.post("/catalog/categories", headers=manager, json=bad).status_code == 422
    dup = {**GEARBOX, "code": "chain", "measurement_profile": [GEARBOX["measurement_profile"][0]] * 2}
    assert client.post("/catalog/categories", headers=manager, json=dup).status_code == 422
    # Miktarla izlenen tipte ölçüm olmaz
    qty = {**GEARBOX, "code": "grease", "is_serialized": False}
    assert client.post("/catalog/categories", headers=manager, json=qty).status_code == 422
    # Ortak tip değiştirilemez, başka firmanınki görünmez
    tire = next(c for c in client.get("/catalog/categories", headers=manager).json() if c["code"] == "tire")
    assert client.patch(f"/catalog/categories/{tire['id']}", headers=manager, json={"name": "Teker"}).status_code == 403
    assert client.delete(f"/catalog/categories/{tire['id']}", headers=manager).status_code == 403
    assert client.patch(f"/catalog/categories/{gearbox['id']}", headers=other, json={"name": "X2"}).status_code == 404


def test_parca_tipi_guncellenir(client, manager, gearbox):
    r = client.patch(f"/catalog/categories/{gearbox['id']}", headers=manager, json={
        "name": "Şanzıman / dişli kutusu",
        "measurement_profile": [{"metric": "oil_temp_c", "label": "Yağ sıcaklığı", "unit": "°C", "required": True}]})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Şanzıman / dişli kutusu" and len(r.json()["measurement_profile"]) == 1
    assert r.json()["required_photo_angles"] == ["overall"]  # gönderilmeyen alan değişmez


def test_sablon_olusur(client, manager, template):
    assert template["is_library"] is False and template["model_count"] == 0
    assert [p["code"] for p in template["positions"]] == [p["code"] for p in POSITIONS]
    rim = next(p for p in template["positions"] if p["code"] == "A1-L-J")
    assert rim["x"] is None and rim["y"] is None
    listed = next(t for t in client.get("/catalog/templates", headers=manager).json() if t["id"] == template["id"])
    assert len(listed["positions"]) == 4


def test_sablon_kurallari(client, manager, tech, other, template):
    body = {"name": "Deneme", "layout": "generic", "positions": POSITIONS}
    assert client.post("/catalog/templates", headers=tech, json=body).status_code == 403
    for bad in (
        [POSITIONS[0], POSITIONS[0]],                                   # aynı kod iki kez
        [{**POSITIONS[0], "category_code": "yok_boyle"}],               # bilinmeyen tip
        [{**POSITIONS[0], "category_code": "filter"}],                  # miktarla izlenen tip takılamaz
        [{**POSITIONS[0], "code": "a1 l"}],                             # geçersiz kod
        [{**POSITIONS[0], "y": None}],                                  # x var, y yok
        [{**POSITIONS[0], "x": 120}],                                   # şema dışı
        [],
    ):
        r = client.post("/catalog/templates", headers=manager, json={**body, "positions": bad})
        assert r.status_code == 422, (bad, r.text)
    # Ortak şablon değiştirilemez; başka firmanın şablonu görünmez
    lib = next(t for t in client.get("/catalog/templates", headers=manager).json() if t["is_library"])
    assert client.put(f"/catalog/templates/{lib['id']}", headers=manager, json=body).status_code == 403
    assert client.delete(f"/catalog/templates/{lib['id']}", headers=manager).status_code == 403
    assert client.put(f"/catalog/templates/{template['id']}", headers=other, json=body).status_code == 404
    assert template["id"] not in {t["id"] for t in client.get("/catalog/templates", headers=other).json()}


def test_sablon_makinede_calisir_ve_takili_pozisyon_korunur(client, manager, tech, gearbox, template):
    model = client.post("/catalog/asset-models", headers=manager, json={
        "manufacturer": "Metso", "model": "LT106", "category": "other", "template_id": template["id"]}).json()
    asset = client.post("/assets", headers=manager, json={"code": "KR-01", "model_id": model["id"], "meter_hours": 500}).json()
    part = client.post("/catalog/parts", headers=manager, json={
        "category_code": "gearbox", "name": "ZF 4WG-260", "expected_life_hours": 12000})
    assert part.status_code == 201, part.text
    item = client.post("/parts", headers=tech, json={"part_id": part.json()["id"], "items": [{"serial_no": "ZF-0001"}]}).json()[0]
    r = client.post(f"/parts/{item['id']}/install", headers=tech, json={"asset_id": asset["id"], "position": "GEARBOX"})
    assert r.status_code == 200, r.text

    # Makine şeması firmanın şablonundan gelir
    detail = client.get(f"/assets/{asset['id']}", headers=tech).json()
    slot = next(p for p in detail["positions"] if p["code"] == "GEARBOX")
    assert slot["serial_no"] == "ZF-0001" and float(slot["x"]) == 55

    # Kontrol kâğıdı firmanın ölçüm profilini ister
    ins = client.post("/inspections", headers=tech, json={"asset_id": asset["id"], "asset_hours": 510})
    assert ins.status_code == 201, ins.text
    sheet = client.get(f"/inspections/{ins.json()['id']}/sheet", headers=tech).json()
    it = next(i for i in sheet["items"] if i["position"] == "GEARBOX")
    assert [m["metric"] for m in it["profile"]] == ["oil_temp_c"] and it["required_angles"] == ["overall"]

    # Takılı pozisyon silinemez, tipi değiştirilemez
    without = [p for p in POSITIONS if p["code"] != "GEARBOX"]
    r = client.put(f"/catalog/templates/{template['id']}", headers=manager,
                   json={"name": template["name"], "layout": "generic", "positions": without})
    assert r.status_code == 409 and "KR-01 GEARBOX" in r.json()["detail"]
    # Boş pozisyon silinir, yenisi eklenir, konum değişir
    moved = [{**p, "x": 60} if p["code"] == "GEARBOX" else p for p in POSITIONS if p["code"] != "A1-R"]
    moved.append({"code": "PUMP", "label": "Pompa", "category_code": "hyd_pump", "x": 70, "y": 40})
    r = client.put(f"/catalog/templates/{template['id']}", headers=manager,
                   json={"name": "Kırıcı v2", "layout": "loader", "positions": moved})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["name"] == "Kırıcı v2" and t["layout"] == "loader" and t["model_count"] == 1
    assert {p["code"] for p in t["positions"]} == {"A1-L", "A1-L-J", "GEARBOX", "PUMP"}

    # Kullanılan şablon ve tip silinemez
    assert client.delete(f"/catalog/templates/{template['id']}", headers=manager).status_code == 409
    assert client.delete(f"/catalog/categories/{gearbox['id']}", headers=manager).status_code == 409


def test_kullanilmayan_tip_ve_sablon_silinir(client, manager):
    cat = client.post("/catalog/categories", headers=manager, json={"code": "chain", "name": "Zincir"}).json()
    tpl = client.post("/catalog/templates", headers=manager, json={
        "name": "Geçici", "positions": [{"code": "CHAIN", "label": "Zincir", "category_code": "chain"}]}).json()
    # Şablonda kullanılan tip silinemez
    assert client.delete(f"/catalog/categories/{cat['id']}", headers=manager).status_code == 409
    assert client.delete(f"/catalog/templates/{tpl['id']}", headers=manager).status_code == 204
    assert client.delete(f"/catalog/categories/{cat['id']}", headers=manager).status_code == 204
    assert "chain" not in {c["code"] for c in client.get("/catalog/categories", headers=manager).json()}
