"""Jant uyumluluğu ve uygulama içi bildirimler."""

from conftest import asset_id, auth, part_id


def test_jant_listesi_aciliyete_gore(client, manager):
    rows = client.get("/rims/compliance", headers=manager).json()
    assert [r["compliance"] for r in rows[:2]] == ["overdue", "due_soon"]
    first, second = rows[0], rows[1]
    assert (first["asset_code"], first["current_position"]) == ("LD-07", "A1-L-J")
    assert first["last_ndt_at"] is None and float(first["hours_to_due"]) == 4000 - 12480
    assert second["last_ndt_at"] is not None and float(second["hours_to_due"]) == 320  # 4000 - 3680
    assert first["asset_id"] and first["part_name"]


def test_ndt_kaydi_jantı_guncel_yapar(client, tech):
    rim = part_id(client, tech, "TR25-0151")
    assert client.post(f"/parts/{rim}/events", headers=tech, json={"event": "inspected", "reason": "ndt", "notes": "Çatlak yok"}).status_code == 200
    r = next(x for x in client.get("/rims/compliance", headers=tech).json() if x["serial_no"] == "TR25-0151")
    assert r["compliance"] == "ok" and float(r["hours_since_ndt"]) == 0


def test_lastik_pozisyonuna_jant_jant_pozisyonuna_lastik_takilamaz(client, manager):
    stock_rim = part_id(client, manager, "TR25-0107")
    ld09 = asset_id(client, manager, "LD-09")
    r = client.post(f"/parts/{stock_rim}/install", headers=manager, json={"asset_id": ld09, "position": "A1-L"})
    assert r.status_code == 422 and "bekliyor" in r.json()["detail"]


def test_bildirimler_ve_okundu(client, manager, tech):
    n = client.get("/notifications", headers=manager).json()
    kinds = {i["kind"] for i in n["items"]}
    assert {"part_critical", "rim_ndt", "stock_low"} <= kinds
    assert n["unread"] == len(n["items"])
    assert n["items"][0]["severity"] == "critical"  # kritikler önce
    rim = next(i for i in n["items"] if i["kind"] == "rim_ndt" and "yaklaşıyor" in i["title"])
    assert rim["title"] == "LD-07 A1-R-J jant muayenesi yaklaşıyor"
    assert rim["link"]["type"] == "rim"
    crit = next(i for i in n["items"] if i["kind"] == "part_critical" and "A2-L" in i["title"])
    assert "Diş %13" in crit["body"] and "539 saat" in crit["body"]

    # Biri okundu
    assert client.post("/notifications/read", headers=manager, json={"keys": [rim["key"]]}).json()["marked"] == 1
    n2 = client.get("/notifications", headers=manager).json()
    assert n2["unread"] == n["unread"] - 1
    assert next(i for i in n2["items"] if i["key"] == rim["key"])["read"] is True
    # Okundu bilgisi kişiseldir: teknisyen için hâlâ okunmamış
    t = client.get("/notifications", headers=tech).json()
    assert next(i for i in t["items"] if i["key"] == rim["key"])["read"] is False

    # Tümü okundu
    client.post("/notifications/read", headers=manager, json={"all": True})
    assert client.get("/notifications", headers=manager).json()["unread"] == 0


def test_durum_degisince_bildirim_yeniden_okunmamis_olur(client, manager):
    client.post("/notifications/read", headers=manager, json={"all": True})
    # Stok değişti: 29.5R25 için 1 lastik daha teslim alındı → hâlâ düşük ama farklı durum
    cat = client.get(f"/parts/{part_id(client, manager, 'MX29-0601')}", headers=manager).json()["part_id"]
    client.post("/parts", headers=manager, json={"part_id": cat, "items": [{"serial_no": "MX29-0999"}]})
    n = client.get("/notifications", headers=manager).json()
    stock = [i for i in n["items"] if i["kind"] == "stock_low" and "29.5R25" in i["title"]]
    # 2 adet oldu = kritik seviye (2): artık uyarı yok
    assert stock == []
    assert n["unread"] == 0


def test_baska_firma_bildirimleri_gormez(client, other):
    n = client.get("/notifications", headers=other).json()
    assert all("LD-07" not in i["title"] for i in n["items"])


def test_uzun_suredir_kontrol_edilmeyen_makine(client, manager):
    from sparetwin.db import owner_tx

    with owner_tx() as conn:  # RS-02'nin son kontrolünü 45 gün öncesine çek
        conn.execute("""update public.inspections set completed_at = now() - interval '45 days'
                         where asset_id = (select id from public.assets where code = 'RS-02')""")
    titles = [i["title"] for i in client.get("/notifications", headers=manager).json()["items"] if i["kind"] == "asset_stale"]
    assert titles == ["RS-02 45 gündür kontrol edilmedi"]
