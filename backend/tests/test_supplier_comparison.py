"""Tedarikçi karşılaştırma: ek veri girişi olmadan, sipariş ve teslim alma kayıtlarından."""

import pytest

FILTER = "51111111-0000-0000-0000-000000000011"   # Volvo: 4 geçmiş + 1 açık sipariş; Ege: 2 geçmiş sipariş
OIL = "51111111-0000-0000-0000-000000000012"      # Ege: 3 sipariş (ucuz ve hızlı); Volvo: 1
SEAL = "51111111-0000-0000-0000-000000000013"     # yalnızca Volvo
VOLVO = "61111111-0000-0000-0000-000000000001"
MICHELIN = "61111111-0000-0000-0000-000000000002"
EGE = "61111111-0000-0000-0000-000000000003"


def compare(client, headers, **params):
    r = client.get("/purchasing/supplier-comparison", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def by_supplier(part):
    return {s["supplier_id"]: s for s in part["suppliers"]}


def test_kalem_bazinda_kimden_kac_kez_kaca_kac_gunde(client, manager):
    rep = compare(client, manager)
    assert rep["months"] == 12
    parts = {p["part_id"]: p for p in rep["parts"]}
    f = by_supplier(parts[FILTER])
    volvo, ege = f[VOLVO], f[EGE]
    # Kaç kez: açık (henüz gelmemiş) sipariş de alım sayılır, teslim ölçülerine girmez
    assert volvo["order_count"] == 5 and ege["order_count"] == 2 and parts[FILTER]["order_count"] == 7
    assert float(volvo["qty"]) == 56 and volvo["delivered"] == 4
    # Fiyat: miktar ağırlıklı ortalama ve son alış
    assert float(volvo["avg_cost"]) == pytest.approx((12 * 84 + 12 * 84 + 10 * 86 + 12 * 88 + 10 * 84) / 56, abs=0.001)
    assert float(volvo["last_cost"]) == 84 and float(ege["avg_cost"]) == pytest.approx(78.5)
    # Teslim: sipariş tarihinden son teslimata; söz verilen tarihe göre zamanında
    assert float(volvo["avg_lead_days"]) == pytest.approx(6.75, abs=0.01) and (volvo["on_time"], volvo["timed"]) == (3, 4)
    assert float(ege["avg_lead_days"]) == pytest.approx(14.5, abs=0.01) and (ege["on_time"], ege["timed"]) == (0, 2)
    # Avantaj: ucuz olan Ege, hızlı olan Volvo
    assert ege["cheapest"] and not ege["fastest"] and volvo["fastest"] and not volvo["cheapest"]

    oil = by_supplier(parts[OIL])
    assert oil[EGE]["cheapest"] and oil[EGE]["fastest"] and oil[EGE]["order_count"] == 3
    # Tek tedarikçili kalemde kimse işaretlenmez
    seal = parts[SEAL]["suppliers"]
    assert len(seal) == 1 and not seal[0]["cheapest"] and not seal[0]["fastest"]
    # Karşılaştırılabilir kalemler önce gelir
    assert [len(p["suppliers"]) for p in rep["parts"]] == sorted((len(p["suppliers"]) for p in rep["parts"]), reverse=True)


def test_tedarikci_ozeti_ve_sabit_sira(client, manager):
    rep = compare(client, manager)
    assert [s["supplier_id"] for s in rep["suppliers"]][:3] == [VOLVO, MICHELIN, EGE]  # renk sırası: kayıt sırası
    s = {x["supplier_id"]: x for x in rep["suppliers"]}
    assert s[VOLVO]["order_count"] == 8 and s[VOLVO]["part_count"] == 3     # filtre 4 + yağ 1 + keçe 2 + açık 1
    assert (s[VOLVO]["on_time"], s[VOLVO]["timed"]) == (5, 7)
    assert s[EGE]["order_count"] == 6 and (s[EGE]["on_time"], s[EGE]["timed"]) == (3, 6)
    assert float(s[MICHELIN]["spend"]) == 2 * 9800 + 4 * 9650 + 2 * 9700


def test_donem_ve_kalem_suzgeci(client, manager, other):
    # Son 3 ay: filtrede yalnızca Volvo'nun son siparişi ve açık sipariş kalır
    short = {p["part_id"]: p for p in compare(client, manager, months=3)["parts"]}
    assert [s["supplier_id"] for s in short[FILTER]["suppliers"]] == [VOLVO] and short[FILTER]["order_count"] == 2
    one = compare(client, manager, part_id=OIL)
    assert [p["part_id"] for p in one["parts"]] == [OIL]
    assert all(s["order_count"] == 0 for s in one["suppliers"] if s["supplier_id"] == MICHELIN)
    assert client.get("/purchasing/supplier-comparison", headers=manager, params={"months": 0}).status_code == 422
    # Başka firma bu veriyi görmez
    rep = compare(client, other)
    assert rep["parts"] == [] and rep["suppliers"] == []


def test_talep_ve_kismi_teslim_sayilmaz(client, manager, tech):
    before = by_supplier({p["part_id"]: p for p in compare(client, manager)["parts"]}[SEAL])[VOLVO]
    # Talep (henüz sipariş verilmedi) karşılaştırmaya girmez
    o = client.post("/purchasing/orders", headers=tech, json={
        "supplier_id": VOLVO, "lines": [{"part_id": SEAL, "qty": 4, "unit_cost": 300}]}).json()
    assert by_supplier({p["part_id"]: p for p in compare(client, manager)["parts"]}[SEAL])[VOLVO]["order_count"] == before["order_count"]
    # Sipariş verilince alım sayılır; kısmi teslim "teslim edildi" değildir
    assert client.post(f"/purchasing/orders/{o['id']}/status", headers=manager, json={"status": "ordered"}).status_code == 200
    line = o["lines"][0]["id"]
    r = client.post(f"/purchasing/orders/{o['id']}/receive", headers=tech, json={"lines": [{"line_id": line, "qty": 1}]})
    assert r.status_code == 200, r.text
    mid = by_supplier({p["part_id"]: p for p in compare(client, manager)["parts"]}[SEAL])[VOLVO]
    assert mid["order_count"] == before["order_count"] + 1 and mid["delivered"] == before["delivered"]
    assert float(mid["last_cost"]) == 300
    # Kalanı kapatılan satır eksik teslim sayılır, teslim süresine girmez
    assert client.post(f"/purchasing/orders/{o['id']}/status", headers=manager, json={"status": "received"}).status_code == 200
    end = by_supplier({p["part_id"]: p for p in compare(client, manager)["parts"]}[SEAL])[VOLVO]
    assert end["short"] == before["short"] + 1 and end["delivered"] == before["delivered"]
