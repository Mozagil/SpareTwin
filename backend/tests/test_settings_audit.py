"""Firma eşikleri, bildirim durumu (üstlen / gizle) ve denetim kaydı (0013)."""

from conftest import asset_id, part_id


def _item(client, headers, pred, **params):
    n = client.get("/notifications", headers=headers, params=params).json()
    return next((i for i in n["items"] if pred(i)), None), n


# ---------- Eşikler ----------

def test_varsayilan_esikler(client, manager):
    o = client.get("/organization", headers=manager).json()
    assert o["name"].startswith("Demo") and o["currency"] == "USD"
    assert o["thresholds"] == {"critical_pct": 20, "watch_pct": 40, "rim_due_soon_pct": 90, "inspection_interval_days": 30}
    assert o["defaults"] == o["thresholds"]


def test_kritik_esigi_dusunce_lastik_izlemeye_iner(client, manager):
    # LD-07 A2-L lastiği %13 dişle kritik
    crit, _ = _item(client, manager, lambda i: i["kind"] == "part_critical" and "A2-L" in i["title"])
    assert crit is not None and "Diş %13" in crit["body"]

    r = client.patch("/organization", headers=manager, json={"thresholds": {"critical_pct": 10, "watch_pct": 40}})
    assert r.status_code == 200, r.text
    assert r.json()["thresholds"]["critical_pct"] == 10
    crit2, _ = _item(client, manager, lambda i: i["kind"] == "part_critical" and "A2-L" in i["title"])
    assert crit2 is None  # artık kritik değil
    ld07 = asset_id(client, manager, "LD-07")
    a2l = next(p for p in client.get(f"/assets/{ld07}", headers=manager).json()["positions"] if p["code"] == "A2-L")
    assert a2l["band"] == "watch"

    # Geri al: eski durum
    client.patch("/organization", headers=manager, json={"thresholds": {"critical_pct": 20, "watch_pct": 40}})
    crit3, _ =_item(client, manager, lambda i: i["kind"] == "part_critical" and "A2-L" in i["title"])
    assert crit3 is not None


def test_esik_dogrulama(client, manager):
    bad = client.patch("/organization", headers=manager, json={"thresholds": {"critical_pct": 50, "watch_pct": 40}})
    assert bad.status_code == 422 and "küçük olmalı" in bad.text
    bad = client.patch("/organization", headers=manager, json={"thresholds": {"inspection_interval_days": 0}})
    assert bad.status_code == 422


def test_teknisyen_esik_degistiremez(client, tech):
    assert client.get("/organization", headers=tech).status_code == 200  # okur
    assert client.patch("/organization", headers=tech, json={"name": "Başka Ad"}).status_code == 403


def test_kontrol_araligi_firmaya_gore(client, manager):
    from sparetwin.db import owner_tx

    with owner_tx() as conn:  # RS-02'nin son kontrolünü 45 gün öncesine çek
        conn.execute("""update public.inspections set completed_at = now() - interval '45 days'
                         where asset_id = (select id from public.assets where code = 'RS-02')""")
    stale, _ = _item(client, manager, lambda i: i["kind"] == "asset_stale" and i["title"].startswith("RS-02"))
    assert stale is not None and "30 günde bir" in stale["body"]
    client.patch("/organization", headers=manager, json={"thresholds": {"inspection_interval_days": 60}})
    stale2, _ = _item(client, manager, lambda i: i["kind"] == "asset_stale" and i["title"].startswith("RS-02"))
    assert stale2 is None
    client.patch("/organization", headers=manager, json={"thresholds": {"inspection_interval_days": 30}})


def test_jant_yaklasiyor_esigi(client, manager):
    # LD-07 A1-R-J: 3680 / 4000 saat = %92 → varsayılan %90 ile "yaklaşıyor"
    rim = next(r for r in client.get("/rims/compliance", headers=manager).json() if r["current_position"] == "A1-R-J")
    assert rim["compliance"] == "due_soon"
    client.patch("/organization", headers=manager, json={"thresholds": {"rim_due_soon_pct": 95}})
    rim = next(r for r in client.get("/rims/compliance", headers=manager).json() if r["current_position"] == "A1-R-J")
    assert rim["compliance"] == "ok"
    client.patch("/organization", headers=manager, json={"thresholds": {"rim_due_soon_pct": 90}})


# ---------- Bildirim durumu ----------

def test_ustlenme_ekip_icin_gecerli(client, manager, tech):
    client.post("/notifications/read", headers=manager, json={"all": True})
    client.post("/notifications/read", headers=tech, json={"all": True})
    rim, n0 = _item(client, tech, lambda i: i["kind"] == "rim_ndt" and "yaklaşıyor" in i["title"])
    assert rim["state"] is None
    r = client.post("/notifications/state", headers=tech, json={"key": rim["key"], "state": "acknowledged", "note": "Servis arandı"})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "acknowledged" and r.json()["note"] == "Servis arandı"
    assert r.json()["state_by"] and r.json()["state_at"]
    # Yönetici de görür; üstlenilen bildirim "yeni" sayılmaz
    m, nm = _item(client, manager, lambda i: i["key"] == rim["key"])
    assert m["state"] == "acknowledged" and m["read"] is True and m["state_by"] == r.json()["state_by"]
    # Geri al
    assert client.post("/notifications/state", headers=tech, json={"key": rim["key"], "state": None}).json()["state"] is None


def test_gizlenen_listeden_duser_ve_geri_alinir(client, manager):
    stock, n0 = _item(client, manager, lambda i: i["kind"] == "stock_low")
    assert stock is not None
    client.post("/notifications/state", headers=manager, json={"key": stock["key"], "state": "dismissed"})
    gone, n1 = _item(client, manager, lambda i: i["key"] == stock["key"])
    assert gone is None and n1["dismissed"] == 1 and len(n1["items"]) == len(n0["items"]) - 1
    shown, n2 = _item(client, manager, lambda i: i["key"] == stock["key"], include_dismissed=True)
    assert shown["state"] == "dismissed" and len(n2["items"]) == len(n0["items"])
    client.post("/notifications/state", headers=manager, json={"key": stock["key"], "state": None})
    back, _ = _item(client, manager, lambda i: i["key"] == stock["key"])
    assert back is not None and back["state"] is None


def test_durum_degisince_gizleme_duser(client, manager):
    """Yükselme kuralı: gizlenen bildirimin durumu değişince yeniden görünür."""
    from sparetwin.db import owner_tx

    stale, _ = _item(client, manager, lambda i: i["kind"] == "asset_stale" and i["title"].startswith("RS-02"))
    assert stale is not None
    client.post("/notifications/state", headers=manager, json={"key": stale["key"], "state": "dismissed"})
    assert _item(client, manager, lambda i: i["kind"] == "asset_stale" and i["title"].startswith("RS-02"))[0] is None
    with owner_tx() as conn:  # yeni (ama yine eski) bir kontrol tarihi → anahtar değişir
        conn.execute("""update public.inspections set completed_at = now() - interval '50 days'
                         where asset_id = (select id from public.assets where code = 'RS-02')""")
    again, _ = _item(client, manager, lambda i: i["kind"] == "asset_stale" and i["title"].startswith("RS-02"))
    assert again is not None and again["state"] is None and again["key"] != stale["key"]


def test_gecersiz_anahtar_ve_izleyici(client, manager, other):
    assert client.post("/notifications/state", headers=manager, json={"key": "yok:1", "state": "dismissed"}).status_code == 404
    # Başka firma kendi listesinde olmayan anahtarı değiştiremez
    stock, _ = _item(client, manager, lambda i: i["kind"] == "stock_low")
    assert client.post("/notifications/state", headers=other, json={"key": stock["key"], "state": "dismissed"}).status_code == 404


# ---------- Denetim kaydı ----------

def test_denetim_kaydi_degisiklikleri_tutar(client, manager, tech):
    rows = client.get("/audit", headers=manager).json()
    assert rows and rows[0]["at"] >= rows[-1]["at"]
    actions = {(r["entity_type"], r["action"]) for r in rows}
    assert ("auth", "login") in actions
    assert ("organization", "update") in actions
    assert ("notifications", "state") in actions
    org = next(r for r in rows if r["entity_type"] == "organization" and r["detail"] and "thresholds" in r["detail"])
    assert org["user_email"] == "yonetici@demo.sparetwin.dev" and org["status"] == 200 and org["method"] == "PATCH"
    assert "rim_due_soon_pct" in org["detail"]["thresholds"] or "inspection_interval_days" in org["detail"]["thresholds"]
    st = next(r for r in rows if r["entity_type"] == "notifications" and r["status"] == 200)
    assert st["detail"]["notification"] and st["detail"]["state"] in ("acknowledged", "dismissed", None)
    # Başarısız deneme de kaydedilir (404), ama ayrıntısı yoktur
    assert any(r["entity_type"] == "notifications" and r["status"] == 404 for r in rows)
    # Kişisel "okundu" işareti ve GET'ler kaydedilmez
    assert all(r["path"] != "/notifications/read" and r["method"] != "GET" for r in rows)
    # Filtreler
    assert all(r["action"] == "login" for r in client.get("/audit", headers=manager, params={"q": "login"}).json())
    assert len(client.get("/audit", headers=manager, params={"limit": 2}).json()) == 2


def test_denetim_kaydi_yalnizca_yonetici_ve_kendi_firmasi(client, tech, other):
    assert client.get("/audit", headers=tech).status_code == 403
    rows = client.get("/audit", headers=other).json()
    assert rows and all(r["user_email"] == "yonetici@baska.test" for r in rows)
    assert all(r["path"] != "/organization" for r in rows)


def test_denetim_kaydi_parca_islemini_varlikla_eslestirir(client, tech):
    rim = part_id(client, tech, "TR25-0151")
    assert client.post(f"/parts/{rim}/events", headers=tech, json={"event": "inspected", "reason": "ndt"}).status_code == 200
    from conftest import auth

    rows = client.get("/audit", headers=auth(client, "yonetici@demo.sparetwin.dev"), params={"entity_id": rim}).json()
    assert rows and rows[0]["entity_type"] == "parts" and rows[0]["action"] == "events" and rows[0]["entity_id"] == rim
    assert rows[0]["user_email"] == "teknisyen@demo.sparetwin.dev"
