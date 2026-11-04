"""Lastiği jantıyla birlikte takma, rotasyon, jant boşluğu bildirimi, Excel'de jantlar."""

from conftest import asset_id, part_id
from test_import import H as BASE_H, post, xlsx


def positions(client, h, code):
    return {p["code"]: p for p in client.get(f"/assets/{asset_id(client, h, code)}", headers=h).json()["positions"]}


def test_jantiyla_takma_ya_ikisi_ya_hicbiri(client, tech):
    ld07 = asset_id(client, tech, "LD-07")
    client.post(f"/parts/{part_id(client, tech, 'MX29-0298')}/remove", headers=tech,
                json={"reason": "worn_out", "next_status": "scrapped"})
    tire, rim = part_id(client, tech, "MX29-0601"), part_id(client, tech, "TR25-0107")

    # A2-L-J dolu (TR25-0153): jant takılamaz → lastik de takılmamalı
    r = client.post(f"/parts/{tire}/install", headers=tech, json={"asset_id": ld07, "position": "A2-L", "rim_id": rim})
    assert r.status_code == 409 and "A2-L-J dolu" in r.json()["detail"]
    assert client.get(f"/parts/{tire}", headers=tech).json()["status"] == "in_stock"

    # Eski jantı sök, yeni lastiği jantıyla birlikte tak
    client.post(f"/parts/{part_id(client, tech, 'TR25-0153')}/remove", headers=tech, json={"reason": "other"})
    r = client.post(f"/parts/{tire}/install", headers=tech, json={"asset_id": ld07, "position": "A2-L", "rim_id": rim})
    assert r.status_code == 200, r.text
    assert r.json()["rim"]["current_position"] == "A2-L-J"
    pos = positions(client, tech, "LD-07")
    assert pos["A2-L"]["serial_no"] == "MX29-0601" and pos["A2-L-J"]["serial_no"] == "TR25-0107"


def test_rotasyon_yer_degistirir_saatleri_korur(client, tech):
    a1l, a1r = part_id(client, tech, "MX29-0412"), part_id(client, tech, "MX29-0413")
    h_l = client.get(f"/parts/{a1l}", headers=tech).json()["hours_total"]
    h_r = client.get(f"/parts/{a1r}", headers=tech).json()["hours_total"]
    r = client.post(f"/parts/{a1l}/move", headers=tech, json={"position": "A1-R"})
    assert r.status_code == 200, r.text
    assert r.json()["swapped_with"] == a1r
    pos = positions(client, tech, "LD-07")
    assert pos["A1-R"]["serial_no"] == "MX29-0412" and pos["A1-L"]["serial_no"] == "MX29-0413"
    assert client.get(f"/parts/{a1l}", headers=tech).json()["hours_total"] == h_l
    assert client.get(f"/parts/{a1r}", headers=tech).json()["hours_total"] == h_r
    ev = [e["reason_code"] for e in client.get(f"/parts/{a1l}/events", headers=tech).json()[:2]]
    assert "rotation" in ev


def test_rotasyon_kurallari(client, tech):
    tire = part_id(client, tech, "MX29-0412")
    before = positions(client, tech, "LD-07")
    r = client.post(f"/parts/{tire}/move", headers=tech, json={"position": "MAIN-PUMP"})
    assert r.status_code == 422 and "bekliyor" in r.json()["detail"]
    assert positions(client, tech, "LD-07") == before  # hiçbir şey değişmedi
    stock = part_id(client, tech, "BS18-2290")
    assert client.post(f"/parts/{stock}/move", headers=tech, json={"position": "A1-L"}).status_code == 422


def test_jant_kaydi_olmayan_makine_bildirimi(client, manager):
    titles = [i["title"] for i in client.get("/notifications", headers=manager).json()["items"] if i["kind"] == "rim_missing"]
    assert "RS-02: 6 jant kaydı yok" in titles and "FL-14: 4 jant kaydı yok" in titles
    assert not any(t.startswith("LD-07") for t in titles)


def test_excel_ile_jantlar(client, manager):
    H = BASE_H[:13] + ["Jant seri no", "Jant ebadı", "Jant NDT periyodu (saat)"] + BASE_H[13:]
    def row(pos, serial, rim=None, rsize=None, ndt=None, first=False):
        base = ["LD-31", pos, "26.5R25", "Bridgestone", "radyal" if first else None, 40 if first else None,
                6 if first else None, serial, 4000, 0, 30, None, None]
        tail = ["Caterpillar", "980M", "yükleyici", 5200] if first else [None] * 4
        return base + [rim, rsize, ndt] + tail

    bad = [
        row("A1-L", "J-1", "TR25-0151", first=True),         # takılı jant
        row("A1-R", "J-2", "TR25-9999"),                      # yeni jant ama ebat yok
    ]
    e = {r["row"]: " | ".join(r["errors"]) for r in post(client, manager, xlsx(H, bad)).json()["rows"]}
    assert "stokta değil" in e[2] and "Jant ebadı gerekli" in e[3]

    # Kendi stok jantını teslim al (önceki testler TR25-0107'yi takmış olabilir)
    rim_cat = client.get(f"/parts/{part_id(client, manager, 'TR25-0107')}", headers=manager).json()["part_id"]
    client.post("/parts", headers=manager, json={"part_id": rim_cat, "items": [{"serial_no": "TR25-0500"}]})
    good = [
        row("A1-L", "J-1", "TR25-0500", first=True),                       # stoktaki jant
        row("A1-R", "J-2", "TR26-0001", "26x25.00/3.5", 3500),            # yeni jant tipi
        row("A2-L", "J-3", "TR26-0002", "26x25.00/3.5"),                   # aynı yeni tip
        row("A2-R", "J-4"),                                                 # jantsız
    ]
    p = post(client, manager, xlsx(H, good)).json()
    assert p["summary"]["errors"] == 0 and p["summary"]["rims"] == 3
    assert any("muayene geçmişi bilinmiyor" in w for w in p["rows"][1]["warnings"])
    r = post(client, manager, xlsx(H, good), dry_run=False)
    assert r.status_code == 200, r.text
    assert r.json()["created"]["rims"] == 3 and r.json()["created"]["catalog"] == 2  # lastik + jant tipi
    pos = positions(client, manager, "LD-31")
    assert pos["A1-L-J"]["serial_no"] == "TR25-0500" and pos["A2-L-J"]["serial_no"] == "TR26-0002"
    assert pos["A2-R-J"]["part_item_id"] is None
    rims = {x["serial_no"]: x for x in client.get("/rims/compliance", headers=manager).json()}
    assert float(rims["TR26-0001"]["ndt_interval_hours"]) == 3500 and rims["TR26-0001"]["compliance"] == "ok"


def test_ana_adres_dokumana_yonlenir(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/docs"


def test_lastik_panelinde_jant_janti_panelinde_lastik(client, manager):
    # LD-07 A1-R-J jantı (TR25-0152, muayenesi yaklaşan); üzerindeki lastik testlerin sırasına göre değişebilir
    rim = client.get(f"/parts/{part_id(client, manager, 'TR25-0152')}", headers=manager).json()
    assert rim["current_position"] == "A1-R-J" and rim["mounted_tire"]
    tire = client.get(f"/parts/{rim['mounted_tire']['id']}", headers=manager).json()
    assert tire["current_position"] == "A1-R" and tire["rim_slot"] == "A1-R-J"
    assert tire["mounted_rim"]["serial_no"] == "TR25-0152" and tire["mounted_rim"]["compliance"] == "due_soon"
    assert float(tire["mounted_rim"]["hours_to_due"]) == 320
    # Jantı kayıtlı olmayan lastik: yuva var, jant yok
    rs = client.get(f"/parts/{part_id(client, manager, 'BS18-2201')}", headers=manager).json()
    assert rs["rim_slot"] == "A1-LO-J" and rs["mounted_rim"] is None
    # Lastik olmayan parçada bu alanlar boş
    cyl = client.get(f"/parts/{part_id(client, manager, 'VLC-88121')}", headers=manager).json()
    assert cyl["rim_slot"] is None and cyl["mounted_rim"] is None
