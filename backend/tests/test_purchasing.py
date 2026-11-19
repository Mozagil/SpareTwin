"""Satınalma: tedarikçi, öneriler, talep → sipariş → teslim alma, yetki ve izolasyon."""

from conftest import part_id

PO_TIRES = "71111111-0000-0000-0000-000000000001"   # SA-…-0001: 3 × 18.00-25, sipariş verilmiş, gecikmiş
PO_FILTER = "71111111-0000-0000-0000-000000000002"  # SA-…-0002: 10 × hidrolik filtre, taslak
FILTER = "51111111-0000-0000-0000-000000000011"
SEAL = "51111111-0000-0000-0000-000000000013"
SOMA = "21111111-0000-0000-0000-000000000002"
SUPPLIER_OIL = "61111111-0000-0000-0000-000000000002"


def sugg(client, h):
    return {s["name"]: s for s in client.get("/purchasing/suggestions", headers=h).json()}


def stock_qty(client, h, pid):
    return float(next(r for r in client.get("/stock", headers=h).json() if r["part_id"] == pid)["qty"])


def test_oneriler_kritik_seviye_yaklasan_degisim_ve_yoldaki(client, manager):
    s = sugg(client, manager)
    t = s["29.5R25 L-4 radyal"]
    assert float(t["suggested_qty"]) == 2 and t["upcoming"] == 1           # 2 + 1 − 1 − 0
    assert any("LD-07 A2-L (~539 sa)" in r for r in t["reasons"])
    bias = s["18.00-25 E-4 diyagonal"]
    assert float(bias["suggested_qty"]) == 1 and float(bias["on_order"]) == 3  # 4 + 1 − 1 − 3
    assert bias["supplier_name"] == "Anadolu OTR Lastik Ltd."              # son tedarikçi önerilir
    assert float(s["L220H kaldırma silindiri keçe takımı"]["suggested_qty"]) == 1
    assert float(s["L220H hidrolik filtresi"]["suggested_qty"]) == 2       # taslak talep yoldaki sayılmaz
    assert "Motor yağı 15W-40" not in s                                     # stok yeterli


def test_talep_duzenleme_ve_siparis_yetkisi(client, manager, tech):
    r = client.post("/purchase-orders", headers=tech, json={"notes": "Öneriden", "lines": [{"part_id": SEAL, "qty": 2}]})
    assert r.status_code == 201 and r.json()["status"] == "draft"
    po = r.json()["id"]
    assert r.json()["number"].endswith("-0003")
    d = client.get(f"/purchase-orders/{po}", headers=tech).json()
    line = d["lines"][0]
    assert float(line["unit_cost"]) == 340  # boşsa katalog fiyatı
    assert client.patch(f"/purchase-orders/{po}/lines/{line['id']}", headers=tech, json={"qty": 3}).status_code == 200
    assert client.post(f"/purchase-orders/{po}/lines", headers=tech, json={"part_id": FILTER, "qty": 5, "unit_cost": 80}).status_code == 201
    assert len(client.get(f"/purchase-orders/{po}", headers=tech).json()["lines"]) == 2
    # Teknisyen siparişi veremez; yönetici tedarikçisiz veremez
    assert client.post(f"/purchase-orders/{po}/order", headers=tech, json={}).status_code == 403
    r = client.post(f"/purchase-orders/{po}/order", headers=manager, json={})
    assert r.status_code == 422 and "tedarikçi" in r.json()["detail"]
    client.patch(f"/purchase-orders/{po}", headers=tech, json={"supplier_id": SUPPLIER_OIL})
    assert client.post(f"/purchase-orders/{po}/order", headers=manager, json={"expected_date": "2030-01-01"}).json()["status"] == "ordered"
    # Sipariş verildikten sonra satır eklenemez; yoldaki miktar öneriyi kapatır
    assert client.post(f"/purchase-orders/{po}/lines", headers=tech, json={"part_id": FILTER, "qty": 1}).status_code == 409
    assert "L220H kaldırma silindiri keçe takımı" not in sugg(client, manager)
    # Taslak iptal edilebilir
    assert client.post(f"/purchase-orders/{PO_FILTER}/cancel", headers=manager).json()["status"] == "cancelled"


def test_sarf_kismi_teslim_alma(client, manager, tech):
    r = client.post("/purchase-orders", headers=tech, json={"supplier_id": SUPPLIER_OIL, "lines": [{"part_id": FILTER, "qty": 10, "unit_cost": 84}]})
    po = r.json()["id"]
    client.post(f"/purchase-orders/{po}/order", headers=manager, json={})
    line = client.get(f"/purchase-orders/{po}", headers=tech).json()["lines"][0]["id"]
    before = stock_qty(client, tech, FILTER)

    r = client.post(f"/purchase-orders/{po}/receive", headers=tech, json={"site_id": SOMA, "ref": "IRS-9001", "lines": [{"line_id": line, "qty": 6}]})
    assert r.status_code == 200 and r.json()["status"] == "partial"
    assert stock_qty(client, tech, FILTER) == before + 6
    mv = client.get(f"/stock/{FILTER}/movements", headers=tech).json()[0]
    assert mv["kind"] == "in" and mv["ref"] == "IRS-9001" and float(mv["unit_cost"]) == 84
    r = client.post(f"/purchase-orders/{po}/receive", headers=tech, json={"site_id": SOMA, "lines": [{"line_id": line, "qty": 5}]})
    assert r.status_code == 422 and "en fazla 4" in r.json()["detail"]
    assert client.post(f"/purchase-orders/{po}/cancel", headers=manager).status_code == 409  # kısmen teslim alındı
    r = client.post(f"/purchase-orders/{po}/receive", headers=tech, json={"site_id": SOMA, "lines": [{"line_id": line, "qty": 4}]})
    assert r.json()["status"] == "received"
    assert client.get(f"/purchase-orders/{po}", headers=tech).json()["received_at"] is not None


def test_seri_numarali_teslim_alma_ve_gecikme_bildirimi(client, manager, tech):
    titles = [i["title"] for i in client.get("/notifications", headers=manager).json()["items"] if i["kind"] == "po_late"]
    assert len(titles) == 1 and "teslimatı 5 gün gecikti" in titles[0]
    line = client.get(f"/purchase-orders/{PO_TIRES}", headers=tech).json()["lines"][0]["id"]

    r = client.post(f"/purchase-orders/{PO_TIRES}/receive", headers=tech,
                    json={"site_id": None, "lines": [{"line_id": line, "qty": 3, "serials": ["N-1", "N-2"]}]})
    assert r.status_code == 422 and "3 seri no girin (girilen 2)" in r.json()["detail"]
    # Var olan seri no: hiçbir şey yazılmaz
    r = client.post(f"/purchase-orders/{PO_TIRES}/receive", headers=tech,
                    json={"lines": [{"line_id": line, "qty": 3, "serials": ["N-1", "N-2", "BS18-2290"]}]})
    assert r.status_code == 409
    assert client.get(f"/purchase-orders/{PO_TIRES}", headers=tech).json()["status"] == "ordered"

    r = client.post(f"/purchase-orders/{PO_TIRES}/receive", headers=tech,
                    json={"site_id": "21111111-0000-0000-0000-000000000001", "lines": [{"line_id": line, "qty": 3, "serials": ["BS18-3001", "BS18-3002", "BS18-3003"]}]})
    assert r.status_code == 200 and r.json()["status"] == "received" and len(r.json()["part_ids"]) == 3
    p = client.get(f"/parts/{part_id(client, tech, 'BS18-3002')}", headers=tech).json()
    assert p["status"] == "in_stock" and float(p["cost_total"]) == 3150
    assert "teslim alındı" in client.get(f"/parts/{p['id']}/events", headers=tech).json()[0]["notes"]
    assert not [i for i in client.get("/notifications", headers=manager).json()["items"] if i["kind"] == "po_late"]
    # Teslim alınmış belge tekrar teslim alınamaz
    assert client.post(f"/purchase-orders/{PO_TIRES}/receive", headers=tech, json={"lines": [{"line_id": line, "qty": 1}]}).status_code == 409


def test_tedarikci_ve_izolasyon(client, manager, tech, other):
    assert client.post("/suppliers", headers=tech, json={"name": "Yetkisiz"}).status_code == 403
    r = client.post("/suppliers", headers=manager, json={"name": "Karadeniz Akü", "phone": "+90 462 000 00 00"})
    assert r.status_code == 201
    assert {s["name"] for s in client.get("/suppliers", headers=manager).json()} >= {"Karadeniz Akü", "Anadolu OTR Lastik Ltd."}
    assert client.get("/suppliers", headers=other).json() == []
    assert client.get("/purchase-orders", headers=other).json() == []
    assert client.get(f"/purchase-orders/{PO_TIRES}", headers=other).status_code == 404
    r = client.post("/purchase-orders", headers=other, json={"supplier_id": SUPPLIER_OIL, "lines": [{"part_id": FILTER, "qty": 1}]})
    assert r.status_code == 404  # başka firmanın tedarikçisi ve kalemi
