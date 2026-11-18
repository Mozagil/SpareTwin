"""Üretilebilirlik ve tedarik açığı: çok seviyeli netleştirme, alt montaj stoku, yoldaki sipariş."""

PRODUCT = "51111111-0000-0000-0000-000000000008"    # KB-BOOM-450 (ürün)
SUB = "51111111-0000-0000-0000-000000000005"        # VOE-LIFT-220 (alt montaj)
PUMP = "51111111-0000-0000-0000-000000000007"       # A10VO-140
FILTER = "51111111-0000-0000-0000-000000000011"     # VOE-11110683 (sarf)
OIL = "51111111-0000-0000-0000-000000000012"        # RIMULA-R4-15W40 (sarf, litre)
SEAL = "51111111-0000-0000-0000-000000000013"       # VOE-SK-LIFT220 (sarf)
URL = "/production/boms"


def stock(client, headers) -> dict:
    return {r["part_id"]: float(r["qty"]) for r in client.get("/stock", headers=headers).json()}


def expected_can_build(s: dict) -> int:
    """Ağaç: ürün = 2 alt montaj + 1 filtre; alt montaj = 1 keçe + 2,5 litre yağ. Alt montaj stoku önce kullanılır."""
    n = 0
    while True:
        made = max(0, 2 * (n + 1) - s[SUB])
        if n + 1 > s[FILTER] or made > s[SEAL] or made * 2.5 > s[OIL]:
            return n
        n += 1


def test_uretilebilirlik_ve_eksikler(client, manager, tech, other):
    top = client.post(URL, headers=manager, json={"part_id": PRODUCT}).json()["id"]
    sub = client.post(URL, headers=manager, json={"part_id": SUB}).json()["id"]
    # Boş ağaçtan üretim çıkmaz
    assert client.get(f"{URL}/{top}/buildable", headers=tech).json()["can_build"] == 0
    for bom, part, qty in ((top, SUB, 2), (top, FILTER, 1), (sub, SEAL, 1), (sub, OIL, "2.5")):
        assert client.post(f"{URL}/{bom}/lines", headers=manager, json={"part_id": part, "qty": qty}).status_code == 201

    # Demo stokta tek keçe takımı var; en az bir ürün çıksın diye stok girilir
    r = client.post("/stock/movements", headers=tech, json={"part_id": SEAL, "kind": "in", "qty": 10, "unit_cost": 340})
    assert r.status_code == 201, r.text
    s = stock(client, tech)
    assert s[FILTER] > 0 and s[SEAL] > 0 and s[OIL] > 0
    can = expected_can_build(s)
    assert can >= 1
    d = client.get(f"{URL}/{top}/buildable", headers=tech).json()
    assert d["can_build"] == can and float(d["qty"]) == 1 and d["short_count"] == 0
    assert all(float(l["shortage"]) == 0 for l in d["lines"])
    rows = {x["part_id"]: x for x in client.get(URL, headers=tech).json()}
    assert rows[PRODUCT]["can_build"] == can
    # Alt montajın kendisi: keçe ve yağ sınırlar
    assert rows[SUB]["can_build"] == int(min(s[SEAL], s[OIL] // 2.5))

    # Üretilebilirden bir fazlası: en az bir kalem eksik, eksik = gerekli − stok
    d = client.get(f"{URL}/{top}/buildable", headers=tech, params={"qty": can + 1}).json()
    assert d["short_count"] >= 1 and d["can_build"] == can
    for l in d["lines"]:
        assert not l["has_bom"] or float(l["shortage"]) == 0   # alt montaj eksik yazılmaz, bileşenlerine açılır
        if float(l["shortage"]) > 0:
            assert abs(float(l["required"]) - float(l["in_stock"]) - float(l["shortage"])) < 0.001
            assert float(l["to_buy"]) == max(float(l["shortage"]) - float(l["on_order"]), 0)
    # Eksikler başta gelir
    flags = [float(l["shortage"]) > 0 for l in d["lines"]]
    assert flags == sorted(flags, reverse=True)

    # Büyük miktar: alt montaj stoku (varsa) kullanılır, kalanı bileşenlerden istenir
    d = client.get(f"{URL}/{top}/buildable", headers=tech, params={"qty": 1000}).json()
    by = {l["part_id"]: l for l in d["lines"]}
    made = 2000 - s[SUB]
    assert abs(float(by[FILTER]["required"]) - 1000) < 0.001 and abs(float(by[FILTER]["shortage"]) - (1000 - s[FILTER])) < 0.001
    assert abs(float(by[SEAL]["required"]) - made) < 0.001 and abs(float(by[OIL]["required"]) - made * 2.5) < 0.001
    if s[SUB] > 0:
        assert by[SUB]["has_bom"] and float(by[SUB]["required"]) == s[SUB] and float(by[SUB]["shortage"]) == 0
    else:
        assert SUB not in by

    assert client.get(f"{URL}/{top}/buildable", headers=tech, params={"qty": 0}).status_code == 422
    assert client.get(f"{URL}/{top}/buildable", headers=other).status_code == 404


def test_yoldaki_siparis_acigi_kapatir(client, manager, tech):
    top = next(x["id"] for x in client.get(URL, headers=tech).json() if x["part_id"] == PRODUCT)
    before = {l["part_id"]: l for l in client.get(f"{URL}/{top}/buildable", headers=tech, params={"qty": 1000}).json()["lines"]}
    base = float(before[FILTER]["on_order"])   # demo veride yolda sipariş olabilir
    supplier = client.post("/purchasing/suppliers", headers=manager, json={"name": "Deneme Tedarik"}).json()["id"]
    po = client.post("/purchasing/orders", headers=manager,
                     json={"supplier_id": supplier, "lines": [{"part_id": FILTER, "qty": 40, "unit_cost": 80}]})
    assert po.status_code == 201, po.text
    # Talep (draft) yolda sayılmaz; sipariş verilince sayılır
    d = {l["part_id"]: l for l in client.get(f"{URL}/{top}/buildable", headers=tech, params={"qty": 1000}).json()["lines"]}
    assert float(d[FILTER]["on_order"]) == base
    r = client.post(f"/purchasing/orders/{po.json()['id']}/status", headers=manager, json={"status": "ordered"})
    assert r.status_code == 200, r.text
    d = {l["part_id"]: l for l in client.get(f"{URL}/{top}/buildable", headers=tech, params={"qty": 1000}).json()["lines"]}
    assert float(d[FILTER]["on_order"]) == base + 40
    assert float(d[FILTER]["shortage"]) == float(before[FILTER]["shortage"])            # eksik stoka göre
    assert float(d[FILTER]["to_buy"]) == float(before[FILTER]["to_buy"]) - 40            # alınacak, yoldakini düşer
