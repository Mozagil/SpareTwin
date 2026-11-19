"""Model parça listesi (BOM): yuvaya uyan kalemler, makine geneli sarf, Excel içe aktarma."""

import io

import pytest
from openpyxl import Workbook, load_workbook

from conftest import asset_id

L220H = "31111111-0000-0000-0000-000000000001"
TIRE_295 = "51111111-0000-0000-0000-000000000001"   # 29.5R25, parça no XLDD2-29.5R25
TIRE_18 = "51111111-0000-0000-0000-000000000002"    # 18.00-25
LIFT_CYL = "51111111-0000-0000-0000-000000000005"   # VOE-LIFT-220
FILTER = "51111111-0000-0000-0000-000000000011"     # VOE-11110683 (sarf)
OIL = "51111111-0000-0000-0000-000000000012"        # RIMULA-R4-15W40 (sarf, litre)
URL = f"/catalog/asset-models/{L220H}/bom"


def xlsx(rows, headers=("Parça no", "Yuva", "Miktar", "Not")) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def upload(client, headers, data, url=URL):
    return client.post(f"{url}/import", headers=headers, files={"file": ("liste.xlsx", data, "application/octet-stream")})


def test_satir_ekleme_ve_kurallar(client, manager, tech, other):
    bom = client.get(URL, headers=tech).json()
    assert bom["lines"] == [] and {"A1-L", "MAIN-PUMP"} <= {s["code"] for s in bom["slots"]}

    assert client.post(URL, headers=tech, json={"part_id": TIRE_295, "position_code": "A1-L"}).status_code == 403
    r = client.post(URL, headers=manager, json={"part_id": TIRE_295, "position_code": "a1-l", "qty": 5})
    assert r.status_code == 201, r.text
    line = r.json()[0]
    assert line["position_code"] == "A1-L" and float(line["qty"]) == 1 and line["position_label"] == "Ön aks sol"
    # Aynı kalem aynı yuvaya iki kez yazılmaz; başka yuvaya ve makine geneline yazılır
    assert client.post(URL, headers=manager, json={"part_id": TIRE_295, "position_code": "A1-L"}).status_code == 409
    assert client.post(URL, headers=manager, json={"part_id": TIRE_295, "position_code": "A1-R"}).status_code == 201
    r = client.post(URL, headers=manager, json={"part_id": FILTER, "qty": 4, "notes": "500 saat bakımı"})
    assert r.status_code == 201 and float(next(x for x in r.json() if x["part_id"] == FILTER)["qty"]) == 4

    for body, code in (
        ({"part_id": TIRE_295, "position_code": "YOK-1"}, 422),          # şablonda olmayan yuva
        ({"part_id": LIFT_CYL, "position_code": "A2-L"}, 422),           # yuva lastik bekliyor
        ({"part_id": FILTER, "position_code": "A2-L"}, 422),             # sarf yuvaya yazılmaz
        ({"part_id": "00000000-0000-0000-0000-000000000000"}, 404),
        ({"part_id": FILTER, "qty": 0}, 422),
    ):
        assert client.post(URL, headers=manager, json=body).status_code == code, body
    # Başka firma ne modeli ne listeyi görür
    assert client.get(URL, headers=other).status_code == 404
    models = {m["id"]: m for m in client.get("/catalog/asset-models", headers=manager).json()}
    assert models[L220H]["bom_count"] == 3


def test_makinede_bos_yuva_ve_takma_onerisi(client, manager, tech):
    # LD-07 A1-L dolu; söküp boşaltınca listedeki kalem "uygun" olarak gelir
    detail = client.get(f"/assets/{asset_id(client, tech, 'LD-07')}", headers=tech).json()
    slot = next(p for p in detail["positions"] if p["code"] == "A1-L")
    assert [f["part_id"] for f in slot["fits"]] == [TIRE_295] and slot["fits"][0]["in_stock"] == 1
    assert next(p for p in detail["positions"] if p["code"] == "A2-L")["fits"] == []   # listeye yazılmadı
    # Stok listesi katalog kalemini taşır: arayüz uyumlu parçaları buradan süzer
    stock = client.get("/parts", headers=tech, params={"status": "in_stock", "category": "tire"}).json()
    assert {p["part_id"] for p in stock} >= {TIRE_295, TIRE_18}


def test_excel_sablonu_ve_ice_aktarma(client, manager, tech):
    r = client.get(f"{URL}/template", headers=manager)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert [c.value for c in wb.worksheets[0][1]] == ["Parça no", "Yuva", "Miktar", "Not"]
    assert "MAIN-PUMP" in {row[0].value for row in wb["Açıklama"].iter_rows()}

    assert upload(client, tech, xlsx([])).status_code == 403
    # Hata varsa hiçbir satır yazılmaz; her hata satır numarasıyla döner
    before = len(client.get(URL, headers=manager).json()["lines"])
    r = upload(client, manager, xlsx([
        ("XLDD2-29.5R25", "A2-L", None, None),
        ("BOYLE-BIR-PARCA-YOK", None, 1, None),
        ("VOE-LIFT-220", "A2-R", None, None),          # yuva lastik bekliyor
        ("RIMULA-R4-15W40", None, "çok", None),
    ]))
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 0 and [e["row"] for e in r.json()["errors"]] == [3, 4, 5]
    assert len(client.get(URL, headers=manager).json()["lines"]) == before

    # Geçerli dosya: başlıklar farklı yazılmış olabilir, parça no büyük/küçük harfe bakmaz, var olan satır yinelenmez
    r = upload(client, manager, xlsx([
        ("xldd2-29.5r25", "A1-L", None, None),          # zaten var
        ("XLDD2-29.5R25", "a2-l", None, None),
        ("VOE-LIFT-220", "LIFT-CYL-L", None, "sol"),
        ("RIMULA-R4-15W40", None, "60,5", "yağ değişimi"),
        (None, None, None, None),                       # boş satır atlanır
    ], headers=("PARÇA NO", "Pozisyon", "Adet", "Açıklama")))
    assert r.status_code == 200 and r.json() == {"added": 3, "existing": 1, "errors": []}
    lines = client.get(URL, headers=manager).json()["lines"]
    oil = next(x for x in lines if x["part_id"] == OIL)
    assert float(oil["qty"]) == 60.5 and oil["position_code"] is None and oil["notes"] == "yağ değişimi"
    assert lines[-1]["position_code"] is None and lines[0]["position_code"] is not None   # yuvalı satırlar önce

    assert upload(client, manager, b"excel degil").status_code == 422
    assert upload(client, manager, xlsx([("X", None, 1, None)], headers=("Ad", "Yuva", "Miktar", "Not"))).status_code == 422


def test_satir_silinir(client, manager, tech):
    lines = client.get(URL, headers=manager).json()["lines"]
    target = next(x for x in lines if x["part_id"] == FILTER)
    assert client.delete(f"{URL}/{target['id']}", headers=tech).status_code == 403
    assert client.delete(f"{URL}/{target['id']}", headers=manager).status_code == 204
    assert client.delete(f"{URL}/{target['id']}", headers=manager).status_code == 404
    assert FILTER not in {x["part_id"] for x in client.get(URL, headers=manager).json()["lines"]}
