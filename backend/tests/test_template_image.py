"""Şablona makine resmi (şema arka planı) ve makine modelinin şablonunu değiştirme."""

import io

import pytest
from PIL import Image

from conftest import asset_id, part_id

POSITIONS = [
    {"code": "A1-L", "label": "Ön sol", "category_code": "tire", "axle": 1, "x": 20, "y": 25},
    {"code": "A1-R", "label": "Ön sağ", "category_code": "tire", "axle": 1, "x": 20, "y": 75},
]


def drawing(w=1200, h=700) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (235, 235, 230)).save(out, format="PNG")
    return out.getvalue()


def upload(client, headers, template_id, data=None):
    return client.put(f"/catalog/templates/{template_id}/image", headers=headers,
                      files={"file": ("ustten.png", data or drawing(), "image/png")})


@pytest.fixture(scope="module")
def template(client, manager):
    r = client.post("/catalog/templates", headers=manager, json={"name": "Çeneli kırıcı", "positions": POSITIONS})
    assert r.status_code == 201, r.text
    assert r.json()["image"] is None
    return r.json()


def test_sablona_resim_yuklenir_ve_makine_semasinda_gelir(client, manager, tech, template):
    r = upload(client, manager, template["id"])
    assert r.status_code == 200, r.text
    got = client.get(r.json()["url"].replace("http://testserver", ""))
    assert got.status_code == 200 and Image.open(io.BytesIO(got.content)).size == (1200, 700)

    listed = next(t for t in client.get("/catalog/templates", headers=tech).json() if t["id"] == template["id"])
    assert listed["image"]["url"]
    # Bu şablonu kullanan makinenin ayrıntısında şema resmi olarak gelir
    model = client.post("/catalog/asset-models", headers=manager, json={
        "manufacturer": "Metso", "model": "C120", "category": "other", "template_id": template["id"]}).json()
    asset = client.post("/assets", headers=manager, json={"code": "KR-02", "model_id": model["id"]}).json()
    assert client.get(f"/assets/{asset['id']}", headers=tech).json()["schematic_image"]["url"]
    # Hazır gövde çizimi kullanan makinede resim yok
    assert client.get(f"/assets/{asset_id(client, tech, 'LD-07')}", headers=tech).json()["schematic_image"] is None
    # Pozisyonlar güncellenince resim yerinde kalır
    r = client.put(f"/catalog/templates/{template['id']}", headers=manager,
                   json={"name": "Çeneli kırıcı", "positions": [{**POSITIONS[0], "x": 30}, POSITIONS[1]]})
    assert r.status_code == 200 and r.json()["image"]["url"]


def test_resim_kurallari(client, manager, tech, other, template):
    assert upload(client, tech, template["id"]).status_code == 403
    assert upload(client, other, template["id"]).status_code == 404           # başka firmanın şablonu
    lib = next(t for t in client.get("/catalog/templates", headers=manager).json() if t["is_library"])
    assert upload(client, manager, lib["id"]).status_code == 404              # ortak şablon değiştirilemez
    assert upload(client, manager, template["id"], b"resim degil").status_code == 415
    # Başka firma listede bu resmi görmez
    assert template["id"] not in {t["id"] for t in client.get("/catalog/templates", headers=other).json()}


def test_resim_silinir(client, manager, template):
    assert upload(client, manager, template["id"]).status_code == 200
    assert client.delete(f"/catalog/templates/{template['id']}/image", headers=manager).status_code == 204
    listed = next(t for t in client.get("/catalog/templates", headers=manager).json() if t["id"] == template["id"])
    assert listed["image"] is None
    assert client.delete(f"/catalog/templates/{template['id']}/image", headers=manager).status_code == 404


def test_model_sablonu_degisir_takili_parca_korunur(client, manager, tech, other):
    templates = client.get("/catalog/templates", headers=manager).json()
    loader = next(t for t in templates if t["is_library"] and t["layout"] == "loader")
    forklift = next(t for t in templates if t["is_library"] and t["layout"] == "forklift")
    model = client.post("/catalog/asset-models", headers=manager, json={
        "manufacturer": "Komatsu", "model": "WA470", "category": "wheel_loader", "template_id": loader["id"]}).json()
    asset = client.post("/assets", headers=manager, json={"code": "LD-21", "model_id": model["id"], "meter_hours": 100}).json()
    url = f"/catalog/asset-models/{model['id']}"

    # Yetki ve kapsam
    assert client.patch(url, headers=tech, json={"template_id": forklift["id"]}).status_code == 403
    assert client.patch(url, headers=other, json={"template_id": forklift["id"]}).status_code == 404
    # Boş makinede şablon serbestçe değişir
    r = client.patch(url, headers=manager, json={"template_id": forklift["id"]})
    assert r.status_code == 200 and r.json()["template_id"] == forklift["id"]
    codes = {p["code"] for p in client.get(f"/assets/{asset['id']}", headers=tech).json()["positions"]}
    assert "BATTERY" in codes and "MAIN-PUMP" not in codes
    assert client.patch(url, headers=manager, json={"template_id": loader["id"]}).status_code == 200

    # Pompa takılı: forklift şablonunda MAIN-PUMP yok → değişmez
    pump = client.post("/catalog/parts", headers=manager, json={
        "category_code": "hyd_pump", "name": "Deneme pompası", "expected_life_hours": 8000}).json()
    item = client.post("/parts", headers=tech, json={"part_id": pump["id"], "items": [{"serial_no": "PMP-21"}]}).json()[0]
    assert client.post(f"/parts/{item['id']}/install", headers=tech,
                       json={"asset_id": asset["id"], "position": "MAIN-PUMP"}).status_code == 200
    r = client.patch(url, headers=manager, json={"template_id": forklift["id"]})
    assert r.status_code == 409 and "LD-21 MAIN-PUMP" in r.json()["detail"]
    # Aynı kodlu ve aynı tipli yuvayı içeren şablona geçilebilir (ortak şablonun kopyası)
    copy = client.post("/catalog/templates", headers=manager, json={
        "name": "Yükleyici (kopya)", "layout": "loader",
        "positions": [{k: p[k] for k in ("code", "label", "category_code", "axle", "x", "y")} for p in loader["positions"]]}).json()
    assert client.patch(url, headers=manager, json={"template_id": copy["id"]}).status_code == 200
    assert part_id(client, tech, "PMP-21") == item["id"]

    # Bilinmeyen model ve bilinmeyen şablon
    assert client.patch("/catalog/asset-models/00000000-0000-0000-0000-000000000000", headers=manager,
                        json={"template_id": loader["id"]}).status_code == 404
    assert client.patch(url, headers=manager, json={"template_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404
