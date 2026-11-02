"""Mobil form için kontrol kâğıdı, devam etme, motor saati düzeltme, iptal."""

import io

from PIL import Image

from conftest import asset_id


def jpg() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (80, 60), (100, 100, 100)).save(b, format="JPEG")
    return b.getvalue()


def test_kontrol_kagidi_ve_ilerleme(client, tech):
    fl14 = asset_id(client, tech, "FL-14")
    iid = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 9400}).json()["id"]
    s = client.get(f"/inspections/{iid}/sheet", headers=tech).json()

    assert s["asset_code"] == "FL-14" and s["layout"] == "forklift"
    items = {it["position"]: it for it in s["items"]}
    assert set(items) == {"A1-L", "A1-R", "A2-L", "A2-R", "MAST-CYL", "BATTERY"}
    assert s["progress"] == {"done": 0, "total": 4}  # yalnızca lastikler zorunlu
    tire = items["A1-L"]
    assert tire["required"] and not tire["started"] and not tire["complete"]
    assert float(tire["previous"]["tread_depth_mm"]["value"]) == 12  # önceki ölçüm ipucu
    assert {m["key"] for m in tire["missing"]} == {"tread_depth_mm", "tread", "sidewall"}
    assert items["MAST-CYL"]["required"] is False  # çökme ölçümü isteğe bağlı

    # Bir lastiği tamamla
    client.put(f"/inspections/{iid}/measurements", headers=tech, json={"items": [
        {"part_item_id": tire["part_item_id"], "metric": "tread_depth_mm", "value": 11.5, "unit": "mm"}]})
    for angle in ("tread", "sidewall"):
        r = client.post(f"/inspections/{iid}/photos", headers=tech, files={"file": ("f.jpg", jpg(), "image/jpeg")},
                        data={"part_item_id": tire["part_item_id"], "angle": angle})
        assert r.status_code == 201
    s = client.get(f"/inspections/{iid}/sheet", headers=tech).json()
    t = next(it for it in s["items"] if it["position"] == "A1-L")
    assert t["complete"] and t["missing"] == [] and float(t["values"]["tread_depth_mm"]) == 11.5
    assert {p["angle"] for p in t["photos"]} == {"tread", "sidewall"} and all(p["url"] for p in t["photos"])
    assert s["progress"] == {"done": 1, "total": 4}

    # Yarım kalan listede görünür
    drafts = client.get("/inspections", headers=tech).json()
    d = next(x for x in drafts if x["id"] == iid)
    assert d["asset_code"] == "FL-14" and d["measured_parts"] == 1 and d["inspected_by_name"] == "Demo Teknisyen"


def test_motor_saati_duzeltme_olcumleri_de_gunceller(client, tech):
    fl14 = asset_id(client, tech, "FL-14")
    iid = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 94000}).json()["id"]  # yanlış: fazladan 0
    s = client.get(f"/inspections/{iid}/sheet", headers=tech).json()
    pid = s["items"][0]["part_item_id"]
    client.put(f"/inspections/{iid}/measurements", headers=tech, json={"items": [
        {"part_item_id": pid, "metric": "tread_depth_mm", "value": 11}]})
    r = client.patch(f"/inspections/{iid}", headers=tech, json={"asset_hours": 9410})
    assert r.status_code == 200 and float(r.json()["asset_hours"]) == 9410
    m = client.get(f"/inspections/{iid}", headers=tech).json()["measurements"]
    assert m and all(True for _ in m)
    hours = client.get(f"/parts/{pid}/measurements", headers=tech, params={"metric": "tread_depth_mm"}).json()
    assert float(next(x for x in hours if x["inspection_id"] == iid)["asset_hours"]) == 9410


def test_iptal(client, tech, other):
    fl14 = asset_id(client, tech, "FL-14")
    iid = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 9420}).json()["id"]
    assert client.get(f"/inspections/{iid}/sheet", headers=other).status_code == 404
    assert client.post(f"/inspections/{iid}/cancel", headers=other).status_code == 404
    assert client.post(f"/inspections/{iid}/cancel", headers=tech).json()["status"] == "rejected"
    assert client.post(f"/inspections/{iid}/complete", headers=tech).status_code == 409
    assert client.patch(f"/inspections/{iid}", headers=tech, json={"asset_hours": 9421}).status_code == 409
    assert iid not in [x["id"] for x in client.get("/inspections", headers=tech).json()]


def test_olcum_ancak_kontrol_tamamlaninca_sayilir(client, tech):
    """Taslak veya iptal edilmiş kontrolün ölçümü sağlık skorunu değiştirmemeli."""
    fl14 = asset_id(client, tech, "FL-14")
    tires = [p for p in client.get(f"/assets/{fl14}", headers=tech).json()["positions"] if p["category_code"] == "tire"]
    target = tires[0]["part_item_id"]
    before = client.get(f"/parts/{target}", headers=tech).json()["tire"]["tread_mm"]

    def fill(iid, value):
        client.put(f"/inspections/{iid}/measurements", headers=tech, json={"items": [
            {"part_item_id": t["part_item_id"], "metric": "tread_depth_mm", "value": value} for t in tires]})
        for t in tires:
            for angle in ("tread", "sidewall"):
                client.post(f"/inspections/{iid}/photos", headers=tech, files={"file": ("f.jpg", jpg(), "image/jpeg")},
                            data={"part_item_id": t["part_item_id"], "angle": angle})

    # 1) Taslak: değişmez
    iid = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 9500}).json()["id"]
    fill(iid, 6)
    assert client.get(f"/parts/{target}", headers=tech).json()["tire"]["tread_mm"] == before
    # 2) İptal: yine değişmez
    client.post(f"/inspections/{iid}/cancel", headers=tech)
    assert client.get(f"/parts/{target}", headers=tech).json()["tire"]["tread_mm"] == before
    # 3) Tamamlanan kontrol: değişir
    iid2 = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 9510}).json()["id"]
    fill(iid2, 10.5)
    assert client.post(f"/inspections/{iid2}/complete", headers=tech).json()["status"] == "completed"
    assert float(client.get(f"/parts/{target}", headers=tech).json()["tire"]["tread_mm"]) == 10.5
    # Önceki değer ipucu da yalnızca tamamlanmış kontrolden gelir
    iid3 = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 9520}).json()["id"]
    item = next(i for i in client.get(f"/inspections/{iid3}/sheet", headers=tech).json()["items"] if i["part_item_id"] == target)
    assert float(item["previous"]["tread_depth_mm"]["value"]) == 10.5
