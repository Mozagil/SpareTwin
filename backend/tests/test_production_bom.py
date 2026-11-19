"""Ürün ağacı (üretim BOM'u): çok seviye, maliyet toplamı, döngü denetimi, Excel içe aktarma."""

import io

from openpyxl import Workbook, load_workbook

PRODUCT = "51111111-0000-0000-0000-000000000008"    # KB-BOOM-450 (ürün)
SUB = "51111111-0000-0000-0000-000000000005"        # VOE-LIFT-220 (alt montaj)
PUMP = "51111111-0000-0000-0000-000000000007"       # A10VO-140
FILTER = "51111111-0000-0000-0000-000000000011"     # VOE-11110683 (sarf)
OIL = "51111111-0000-0000-0000-000000000012"        # RIMULA-R4-15W40 (sarf, litre)
SEAL = "51111111-0000-0000-0000-000000000013"       # VOE-SK-LIFT220 (sarf)
URL = "/production/boms"


def near(a, b) -> bool:
    return abs(float(a) - float(b)) < 0.001


def avg_costs(client, headers) -> dict:
    """Stok ortalama maliyeti: ürün ağacı yaprak maliyetini buradan alır."""
    return {r["part_id"]: float(r["avg_cost"]) for r in client.get("/stock", headers=headers).json() if r["avg_cost"] is not None}


def xlsx(rows, headers=("Ürün parça no", "Bileşen parça no", "Miktar", "Not")) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def upload(client, headers, data):
    return client.post(f"{URL}/import", headers=headers, files={"file": ("agac.xlsx", data, "application/octet-stream")})


def test_agac_kurulur_ve_maliyet_toplanir(client, manager, tech, other):
    assert client.get(URL, headers=tech).json() == []
    assert client.post(URL, headers=tech, json={"part_id": PRODUCT}).status_code == 403
    r = client.post(URL, headers=manager, json={"part_id": PRODUCT})
    assert r.status_code == 201, r.text
    top = r.json()["id"]
    assert client.post(URL, headers=manager, json={"part_id": PRODUCT}).status_code == 409
    assert client.post(URL, headers=manager, json={"part_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404
    sub = client.post(URL, headers=manager, json={"part_id": SUB}).json()["id"]

    assert client.post(f"{URL}/{top}/lines", headers=tech, json={"part_id": SUB, "qty": 2}).status_code == 403
    assert client.post(f"{URL}/{top}/lines", headers=manager, json={"part_id": SUB, "qty": 2}).status_code == 201
    assert client.post(f"{URL}/{top}/lines", headers=manager, json={"part_id": SUB, "qty": 1}).status_code == 409
    assert client.post(f"{URL}/{top}/lines", headers=manager, json={"part_id": FILTER, "qty": 1}).status_code == 201
    assert client.post(f"{URL}/{sub}/lines", headers=manager, json={"part_id": SEAL, "qty": 1}).status_code == 201
    r = client.post(f"{URL}/{sub}/lines", headers=manager, json={"part_id": OIL, "qty": "2.5", "notes": "ilk dolum"})
    c = avg_costs(client, tech)
    lift_cost = c[SEAL] + 2.5 * c[OIL]
    assert r.status_code == 201 and near(r.json()["material_cost"], lift_cost)
    assert client.post(f"{URL}/{top}/lines", headers=manager, json={"part_id": FILTER, "qty": 0}).status_code == 422

    d = client.get(f"{URL}/{top}", headers=tech).json()
    assert near(d["material_cost"], 2 * lift_cost + c[FILTER]) and d["unknown_cost"] == 0
    lift = next(x for x in d["lines"] if x["part_id"] == SUB)
    assert lift["has_bom"] and near(lift["unit_cost"], lift_cost) and near(lift["cost"], 2 * lift_cost)
    oil = next(x for x in lift["children"] if x["part_id"] == OIL)
    assert float(oil["qty"]) == 2.5 and float(oil["total_qty"]) == 5 and oil["notes"] == "ilk dolum"
    assert float(oil["in_stock"]) > 0 and oil["children"] == []
    # Alt montaj hangi üründe geçiyor
    assert [u["part_id"] for u in client.get(f"{URL}/{sub}", headers=tech).json()["used_in"]] == [PRODUCT]

    rows = client.get(URL, headers=tech).json()
    assert [(x["part_id"], x["line_count"], x["is_subassembly"]) for x in rows] == [(PRODUCT, 2, False), (SUB, 2, True)]
    # Başka firma görmez, dokunamaz
    assert client.get(URL, headers=other).json() == []
    assert client.get(f"{URL}/{top}", headers=other).status_code == 404
    assert client.post(f"{URL}/{top}/lines", headers=other, json={"part_id": PUMP, "qty": 1}).status_code == 404


def test_dongu_engellenir(client, manager):
    rows = {x["part_id"]: x["id"] for x in client.get(URL, headers=manager).json()}
    # Ürün kendi içine ve kendisini içeren alt montajın içine yazılamaz
    assert client.post(f"{URL}/{rows[PRODUCT]}/lines", headers=manager, json={"part_id": PRODUCT, "qty": 1}).status_code == 422
    assert client.post(f"{URL}/{rows[SUB]}/lines", headers=manager, json={"part_id": PRODUCT, "qty": 1}).status_code == 422


def test_excel_ice_aktarma(client, manager, tech):
    r = client.get(f"{URL}/template", headers=manager)
    assert r.status_code == 200
    assert [c.value for c in load_workbook(io.BytesIO(r.content)).worksheets[0][1]] == ["Ürün parça no", "Bileşen parça no", "Miktar", "Not"]
    assert upload(client, tech, xlsx([])).status_code == 403

    before = client.get(URL, headers=manager).json()
    r = upload(client, manager, xlsx([
        ("A10VO-140", "VOE-11110683", 2, None),
        ("A10VO-140", "YOK-BOYLE-PARCA", 1, None),
        ("VOE-LIFT-220", "KB-BOOM-450", 1, None),        # döngü
        ("A10VO-140", "RIMULA-R4-15W40", None, None),    # miktar yok
    ]))
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 0 and [e["row"] for e in r.json()["errors"]] == [3, 4, 5]
    assert client.get(URL, headers=manager).json() == before

    # Yeni ürün ağacı dosyadan açılır; var olan satır yinelenmez; dosya içi döngü de yakalanır
    r = upload(client, manager, xlsx([
        ("a10vo-140", "VOE-11110683", 2, "emiş"),
        ("A10VO-140", "RIMULA-R4-15W40", "1,5", None),
        ("KB-BOOM-450", "A10VO-140", 1, None),
        ("KB-BOOM-450", "VOE-LIFT-220", 2, None),        # zaten var
        (None, None, None, None),
    ], headers=("Ürün", "Bileşen", "Adet", "Açıklama")))
    assert r.status_code == 200 and r.json() == {"boms_created": 1, "added": 3, "existing": 1, "errors": []}
    rows = {x["part_id"]: x for x in client.get(URL, headers=manager).json()}
    c = avg_costs(client, tech)
    pump_cost = 2 * c[FILTER] + 1.5 * c[OIL]
    assert rows[PUMP]["is_subassembly"] and near(rows[PUMP]["material_cost"], pump_cost)
    assert near(rows[PRODUCT]["material_cost"], 2 * (c[SEAL] + 2.5 * c[OIL]) + c[FILTER] + pump_cost)

    r = upload(client, manager, xlsx([("VOE-11110683", "VOE-TILT-220", 1, None), ("VOE-TILT-220", "VOE-11110683", 1, None)]))
    assert [e["row"] for e in r.json()["errors"]] == [3]
    assert upload(client, manager, b"excel degil").status_code == 422
    assert upload(client, manager, xlsx([("X", 1)], headers=("Ad", "Miktar"))).status_code == 422


def test_satir_ve_agac_silinir(client, manager, tech):
    rows = {x["part_id"]: x["id"] for x in client.get(URL, headers=manager).json()}
    d = client.get(f"{URL}/{rows[PRODUCT]}", headers=manager).json()
    line = next(x for x in d["lines"] if x["part_id"] == FILTER)["line_id"]
    assert client.delete(f"{URL}/{rows[PRODUCT]}/lines/{line}", headers=tech).status_code == 403
    assert client.delete(f"{URL}/{rows[PRODUCT]}/lines/{line}", headers=manager).status_code == 204
    assert client.delete(f"{URL}/{rows[PRODUCT]}/lines/{line}", headers=manager).status_code == 404
    # Alt montajın ağacı silinince üst üründe satır kalır ama yaprak olur
    assert client.delete(f"{URL}/{rows[SUB]}", headers=tech).status_code == 403
    assert client.delete(f"{URL}/{rows[SUB]}", headers=manager).status_code == 204
    lift = next(x for x in client.get(f"{URL}/{rows[PRODUCT]}", headers=manager).json()["lines"] if x["part_id"] == SUB)
    assert not lift["has_bom"] and lift["children"] == []
