"""Makine ikizini başka firmaya devretme (0024): kod, önizleme, devralma, iptal.

Demo firma (üretici) kendi şablonu, modeli ve parça tipiyle bir makine kurar;
"Başka Firma" (müşteri) kodu girip makineyi parça ikizleri ve geçmişiyle alır.
"""

import io

import psycopg
import pytest
from PIL import Image

from conftest import OTHER_TENANT
from sparetwin.db import user_tx

GEARBOX = {"code": "gearbox", "name": "Şanzıman", "is_serialized": True,
           "measurement_profile": [{"metric": "oil_temp_c", "label": "Yağ sıcaklığı", "unit": "°C"}]}
POSITIONS = [
    {"code": "A1-L", "label": "Ön sol", "category_code": "tire", "axle": 1, "x": 20, "y": 25},
    {"code": "A1-R", "label": "Ön sağ", "category_code": "tire", "axle": 1, "x": 20, "y": 75},
    {"code": "GEARBOX", "label": "Şanzıman", "category_code": "gearbox", "x": 55, "y": 50},
]


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (800, 500), (230, 230, 225)).save(out, format="PNG")
    return out.getvalue()


def _ok(r, code=201):
    assert r.status_code == code, r.text
    return r.json()


def _machine(client, manager, model_id, part, code, serial):
    """Üreticide makine açar, bir şanzıman teslim alıp takar, 50 saat çalıştırır."""
    asset = _ok(client.post("/assets", headers=manager, json={"code": code, "model_id": model_id, "serial_no": f"SN-{code}"}))
    item = _ok(client.post("/parts", headers=manager, json={
        "part_id": part["id"], "items": [{"serial_no": serial}], "purchase_cost": 5000}))[0]
    _ok(client.post(f"/parts/{item['id']}/install", headers=manager,
                    json={"asset_id": asset["id"], "position": "GEARBOX"}), 200)
    _ok(client.post(f"/assets/{asset['id']}/meter", headers=manager, json={"hours": 50}), 200)
    return asset["id"], item["id"]


@pytest.fixture(scope="module")
def built(client, manager):
    _ok(client.post("/catalog/categories", headers=manager, json=GEARBOX))
    template = _ok(client.post("/catalog/templates", headers=manager,
                               json={"name": "Kırıcı şasi", "layout": "generic", "positions": POSITIONS}))
    _ok(client.put(f"/catalog/templates/{template['id']}/image", headers=manager,
                   files={"file": ("ustten.png", _png(), "image/png")}), 200)
    model = _ok(client.post("/catalog/asset-models", headers=manager, json={
        "manufacturer": "Demo Makina", "model": "K-100", "category": "other", "template_id": template["id"]}))
    part = _ok(client.post("/catalog/parts", headers=manager, json={
        "category_code": "gearbox", "name": "Şanzıman ZF 4WG", "manufacturer": "ZF", "part_no": "GB-1",
        "list_cost": 5200, "expected_life_hours": 8000}))
    asset, item = _machine(client, manager, model["id"], part, "KR-01", "GB-0001")
    return {"asset": asset, "item": item, "model": model, "part": part, "template": template}


@pytest.fixture(scope="module")
def transfer(client, manager, built):
    return _ok(client.post(f"/assets/{built['asset']}/transfer", headers=manager, json={"note": "Başka Firma teslimatı"}))


def test_devir_kodu_yonetici_ile_uretilir(client, manager, tech, built, transfer):
    assert transfer["code"].startswith("DV-") and transfer["status"] == "pending"
    assert transfer["asset_code"] == "KR-01" and transfer["part_count"] == 1
    assert transfer["model_name"] == "Demo Makina K-100"
    # Makine sayfasında bekleyen devir yöneticiye koduyla görünür, teknisyene görünmez
    assert client.get(f"/assets/{built['asset']}", headers=manager).json()["transfer"]["code"] == transfer["code"]
    assert client.get(f"/assets/{built['asset']}", headers=tech).json()["transfer"] is None
    assert client.post(f"/assets/{built['asset']}/transfer", headers=tech, json={}).status_code == 403
    # Aynı makine için ikinci bekleyen devir açılmaz
    r = client.post(f"/assets/{built['asset']}/transfer", headers=manager, json={})
    assert r.status_code == 409 and "bekleyen" in r.json()["detail"]


def test_baska_firmanin_makinesi_devredilemez(client, other, built):
    assert client.post(f"/assets/{built['asset']}/transfer", headers=other, json={}).status_code == 404


def test_onizleme_aliciya_ne_alacagini_gosterir(client, manager, other, transfer):
    p = _ok(client.get("/transfers/preview", headers=other, params={"code": transfer["code"].lower()}), 200)
    assert p["from_tenant_name"] == "Demo Liman ve Maden A.Ş." and p["asset_code"] == "KR-01"
    assert p["model_name"] == "Demo Makina K-100" and float(p["meter_hours"]) == 50
    assert p["code_taken"] is False
    assert [(x["position"], x["serial_no"], float(x["hours_total"])) for x in p["parts"]] == [("GEARBOX", "GB-0001", 50.0)]
    # Devreden kendi kodunu kullanamaz; uydurma kod bulunmaz
    assert client.get("/transfers/preview", headers=manager, params={"code": transfer["code"]}).status_code == 422
    assert client.get("/transfers/preview", headers=other, params={"code": "DV-YOKBOYLE"}).status_code == 404


def test_devralma_makineyi_parcalari_ve_gecmisi_tasir(client, manager, other, built, transfer):
    # Alıcının filosunda aynı kod varsa başka kod istenir
    r = client.post("/transfers/accept", headers=other, json={"code": transfer["code"], "asset_code": "BF-01"})
    assert r.status_code == 409 and "BF-01" in r.json()["detail"]

    done = _ok(client.post("/transfers/accept", headers=other, json={"code": transfer["code"], "asset_code": "BF-02"}), 200)
    assert done["asset_id"] == built["asset"] and done["part_count"] == 1
    assert done["from_tenant_name"] == "Demo Liman ve Maden A.Ş." and "copied" not in done

    # Devreden artık makineyi ve parçayı görmez
    assert client.get(f"/assets/{built['asset']}", headers=manager).status_code == 404
    assert client.get(f"/parts/{built['item']}", headers=manager).status_code == 404

    # Alıcıda: aynı makine (aynı id ve QR), yeni filo kodu, sayaç ve takılı parça yerinde
    a = _ok(client.get(f"/assets/{built['asset']}", headers=other), 200)
    assert a["code"] == "BF-02" and float(a["meter_hours"]) == 50 and a["serial_no"] == "SN-KR-01"
    box = next(p for p in a["positions"] if p["code"] == "GEARBOX")
    assert box["part_item_id"] == built["item"] and box["serial_no"] == "GB-0001"
    assert len(a["positions"]) == 3 and a["schematic_image"]["url"]   # şablon resmiyle kopyalandı

    # Geçmiş taşındı, devir olayı eklendi, maliyet geçmedi
    events = client.get(f"/parts/{built['item']}/events", headers=other).json()
    assert {e["event_type"] for e in events} == {"received", "installed", "transferred"}
    moved = next(e for e in events if e["event_type"] == "transferred")
    assert float(moved["part_hours"]) == 50 and "Demo Liman" in moved["notes"] and "Başka Firma" in moved["notes"]
    part = _ok(client.get(f"/parts/{built['item']}", headers=other), 200)
    assert float(part["cost_total"]) == 0 and part["status"] == "installed"
    assert all(e["cost"] is None for e in events)

    # Kod bir kez kullanılır
    assert client.post("/transfers/accept", headers=other, json={"code": transfer["code"]}).status_code == 404


def test_devredene_ozel_tanimlar_alicida_kopyalanir(client, manager, other, built):
    models = [m for m in client.get("/catalog/asset-models", headers=other).json() if m["model"] == "K-100"]
    assert len(models) == 1 and models[0]["is_library"] is False and models[0]["id"] != built["model"]["id"]
    templates = [t for t in client.get("/catalog/templates", headers=other).json() if t["name"] == "Kırıcı şasi"]
    assert len(templates) == 1 and templates[0]["id"] != built["template"]["id"]
    assert [p["code"] for p in templates[0]["positions"]] == ["A1-L", "A1-R", "GEARBOX"]
    cat = next(c for c in client.get("/catalog/categories", headers=other).json() if c["code"] == "gearbox")
    assert cat["is_library"] is False and cat["measurement_profile"][0]["metric"] == "oil_temp_c"
    parts = [p for p in client.get("/catalog/parts", headers=other).json() if p["part_no"] == "GB-1"]
    assert len(parts) == 1 and parts[0]["id"] != built["part"]["id"]
    assert parts[0]["list_cost"] is None and parts[0]["specs"]["expected_life_hours"] == 8000
    # Devredenin kendi tanımları yerinde
    assert any(m["id"] == built["model"]["id"] for m in client.get("/catalog/asset-models", headers=manager).json())


def test_devir_listesi_iki_tarafta_da_gorunur(client, manager, other, built, transfer):
    out = next(t for t in client.get("/transfers", headers=manager).json() if t["id"] == transfer["id"])
    assert (out["direction"], out["status"], out["counterparty"]) == ("out", "accepted", "Başka Firma")
    assert out["code"] is None and out["asset_id"] is None and out["asset_code"] == "KR-01"
    inc = next(t for t in client.get("/transfers", headers=other).json() if t["id"] == transfer["id"])
    assert (inc["direction"], inc["status"], inc["counterparty"]) == ("in", "accepted", "Demo Liman ve Maden A.Ş.")
    assert inc["asset_id"] == built["asset"] and inc["code"] is None


def test_ikinci_makinede_model_ve_katalog_tekrar_kopyalanmaz(client, manager, other, built):
    asset, item = _machine(client, manager, built["model"]["id"], built["part"], "KR-02", "GB-0002")
    t = _ok(client.post(f"/assets/{asset}/transfer", headers=manager, json={}))
    _ok(client.post("/transfers/accept", headers=other, json={"code": t["code"]}), 200)
    assert _ok(client.get(f"/assets/{asset}", headers=other), 200)["code"] == "KR-02"
    assert len([m for m in client.get("/catalog/asset-models", headers=other).json() if m["model"] == "K-100"]) == 1
    assert len([p for p in client.get("/catalog/parts", headers=other).json() if p["part_no"] == "GB-1"]) == 1
    assert len([t for t in client.get("/catalog/templates", headers=other).json() if t["name"] == "Kırıcı şasi"]) == 1


def test_iptal_edilen_kod_kullanilamaz(client, manager, other, built):
    asset, _ = _machine(client, manager, built["model"]["id"], built["part"], "KR-03", "GB-0003")
    t = _ok(client.post(f"/assets/{asset}/transfer", headers=manager, json={}))
    assert client.post(f"/transfers/{t['id']}/cancel", headers=other).status_code == 404
    assert _ok(client.post(f"/transfers/{t['id']}/cancel", headers=manager), 200)["status"] == "cancelled"
    assert client.post(f"/transfers/{t['id']}/cancel", headers=manager).status_code == 422
    assert client.post("/transfers/accept", headers=other, json={"code": t["code"]}).status_code == 404
    assert client.get(f"/assets/{asset}", headers=manager).json()["transfer"] is None
    # İptalden sonra yeni kod üretilebilir
    again = _ok(client.post(f"/assets/{asset}/transfer", headers=manager, json={}))
    assert again["code"] != t["code"]
    _ok(client.post(f"/transfers/{again['id']}/cancel", headers=manager), 200)


def test_acik_is_varken_devredilemez(client, manager, tech, other, built):
    asset, _ = _machine(client, manager, built["model"]["id"], built["part"], "KR-04", "GB-0004")
    insp = _ok(client.post("/inspections", headers=tech, json={"asset_id": asset}))
    r = client.post(f"/assets/{asset}/transfer", headers=manager, json={})
    assert r.status_code == 422 and "kontrol" in r.json()["detail"]
    _ok(client.post(f"/inspections/{insp['id']}/cancel", headers=tech), 200)

    t = _ok(client.post(f"/assets/{asset}/transfer", headers=manager, json={}))
    # Kod üretildikten sonra açılan iş emri de devralmayı durdurur
    wo = _ok(client.post("/maintenance/work-orders", headers=manager, json={
        "asset_id": asset, "kind": "planned", "title": "Teslim öncesi bakım"}))
    r = client.post("/transfers/accept", headers=other, json={"code": t["code"]})
    assert r.status_code == 422 and "iş emri" in r.json()["detail"]
    _ok(client.post(f"/maintenance/work-orders/{wo['id']}/status", headers=manager, json={"status": "cancelled"}), 200)
    _ok(client.post("/transfers/accept", headers=other, json={"code": t["code"]}), 200)


def test_devir_tablosuna_dogrudan_yazilamaz_ve_yabanci_goremez(client, manager, other, tech):
    me = client.get("/auth/me", headers=other).json()["id"]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with user_tx(me) as conn:
            conn.execute("update public.asset_transfers set status = 'pending'")
    with user_tx(me) as conn:
        # Alıcı yalnızca kendisine devredilenleri görür; devredenin bekleyen / iptal kayıtlarını görmez
        rows = conn.execute("select status, to_tenant_id::text as to_id from public.asset_transfers").fetchall()
        assert rows and all(r["status"] == "accepted" and r["to_id"] == OTHER_TENANT for r in rows)
        # Fonksiyon, üyesi olunmayan firma adına çağrılamaz
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("select public.asset_transfer_preview('DV-X', '11111111-1111-1111-1111-111111111111')")
    # Devredende teknisyen kodu göremez
    tech_id = client.get("/auth/me", headers=tech).json()["id"]
    with user_tx(tech_id) as conn:
        assert conn.execute("select count(*) as n from public.asset_transfers").fetchone()["n"] == 0
