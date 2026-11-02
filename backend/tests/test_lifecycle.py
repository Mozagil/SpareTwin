from conftest import asset_id, auth, part_id


def test_filo_ozeti(client, manager):
    fleet = {a["code"]: a for a in client.get("/assets", headers=manager).json()}
    assert set(fleet) == {"LD-07", "LD-09", "RS-02", "FL-14"}
    assert fleet["LD-07"]["critical_parts"] == 2
    assert fleet["LD-09"]["critical_parts"] == 0
    assert fleet["LD-07"]["layout"] == "loader"


def test_makine_semasi_bos_ve_dolu_pozisyonlarla(client, manager):
    a = client.get(f"/assets/{asset_id(client, manager, 'LD-07')}", headers=manager).json()
    pos = {p["code"]: p for p in a["positions"]}
    assert len(pos) == 8
    assert pos["A2-L"]["band"] == "critical"
    assert float(pos["A2-L"]["condition_pct"]) == 12.8
    assert pos["A1-L"]["x"] is not None


def test_lastik_ikizi_detayi(client, manager):
    p = client.get(f"/parts/{part_id(client, manager, 'MX29-0298')}", headers=manager).json()
    assert p["tire"]["size"] == "29.5R25"
    assert float(p["tire"]["tread_mm"]) == 14
    assert p["tire"]["projected_hours_left"] == 539
    assert p["rim"] is None


def test_asinma_egrisi_ve_maliyet_raporu(client, manager):
    w = client.get(f"/parts/{part_id(client, manager, 'MX29-0298')}/wear", headers=manager).json()
    assert [float(p["tread_mm"]) for p in w["points"]] == [55, 22, 14]
    assert [float(p["part_hours"]) for p in w["points"]] == [0, 3048, 3680]  # 2100 + (11848 - 10900), 2100 + 1580
    assert float(w["projection"]["to_hours"]) == 3680 + 539
    # Lastik olmayan parça
    assert client.get(f"/parts/{part_id(client, manager, 'VLC-88121')}/wear", headers=manager).status_code == 404

    cost = {r["code"]: float(r["expected_cost_per_hour"]) for r in client.get("/reports/tire-cost", headers=manager).json()}
    assert cost == {"LD-07": 9.30, "LD-09": 6.76, "RS-02": 5.11, "FL-14": 0.52}


def test_qr_cozumleme(client, manager):
    assert client.get("/qr/ST-A-LD07", headers=manager).json()["type"] == "asset"
    assert client.get("/qr/ST-P-MX29-0412", headers=manager).json()["type"] == "part"
    assert client.get("/qr/YOK", headers=manager).status_code == 404


def test_yanlis_kategori_pozisyonuna_takilamaz(client, tech):
    r = client.post(
        f"/parts/{part_id(client, tech, 'MX29-0601')}/install", headers=tech,
        json={"asset_id": asset_id(client, tech, "LD-07"), "position": "TILT-CYL"},
    )
    assert r.status_code == 422
    assert "bekliyor" in r.json()["detail"]


def test_dolu_pozisyona_takilamaz(client, tech):
    r = client.post(
        f"/parts/{part_id(client, tech, 'MX29-0601')}/install", headers=tech,
        json={"asset_id": asset_id(client, tech, "LD-07"), "position": "A2-L"},
    )
    assert r.status_code == 409
    assert "dolu" in r.json()["detail"]


def test_sayac_geri_gidemez(client, tech):
    r = client.post(f"/assets/{asset_id(client, tech, 'LD-07')}/meter", headers=tech, json={"hours": 100})
    assert r.status_code == 422
    assert "geri gidemez" in r.json()["detail"]


def test_lastik_degisimi_uctan_uca(client, tech):
    ld07 = asset_id(client, tech, "LD-07")
    old, new = part_id(client, tech, "MX29-0298"), part_id(client, tech, "MX29-0601")

    assert client.post(f"/assets/{ld07}/meter", headers=tech, json={"hours": 12510}).status_code == 200

    r = client.post(f"/parts/{old}/remove", headers=tech, json={"reason": "worn_out", "next_status": "scrapped"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scrapped"
    assert float(r.json()["hours_accumulated"]) == 3710  # 2100 + (12510 - 10900)

    r = client.post(f"/parts/{new}/install", headers=tech, json={"asset_id": ld07, "position": "A2-L"})
    assert r.status_code == 200, r.text
    assert float(r.json()["installed_at_hours"]) == 12510

    events = [e["event_type"] for e in client.get(f"/parts/{old}/events", headers=tech).json()]
    assert events[:2] == ["scrapped", "removed"]
    # Olayı kimin yaptığı kaydedildi
    assert client.get(f"/parts/{old}/events", headers=tech).json()[1]["performed_by_name"] == "Demo Teknisyen"


def test_jant_ndt_kaydi(client, tech):
    rim = part_id(client, tech, "TR25-0107")
    r = client.post(f"/parts/{rim}/events", headers=tech, json={"event": "inspected", "reason": "ndt"})
    assert r.status_code == 200, r.text
    rows = client.get("/rims/compliance", headers=tech).json()
    assert rows[0]["compliance"] == "ok"


def test_takma_sokme_olay_ile_yapilamaz(client, tech):
    rim = part_id(client, tech, "TR25-0107")
    r = client.post(f"/parts/{rim}/events", headers=tech, json={"event": "installed"})
    assert r.status_code == 422


def test_izleyici_rolu_yazamaz(client, manager):
    # Yönetici, teknisyeni izleyiciye düşürür (doğrudan veritabanında)
    from sparetwin.db import owner_tx

    with owner_tx() as conn:
        conn.execute(
            """insert into public.app_users (email, password_hash, full_name)
               select 'izleyici@demo.sparetwin.dev', password_hash, 'Demo İzleyici'
                 from public.app_users where email = 'yonetici@demo.sparetwin.dev'"""
        )
        conn.execute(
            """insert into public.memberships (tenant_id, user_id, role)
               select '11111111-1111-1111-1111-111111111111', id, 'viewer'
                 from public.app_users where email = 'izleyici@demo.sparetwin.dev'"""
        )
    viewer = auth(client, "izleyici@demo.sparetwin.dev")
    assert client.get("/assets", headers=viewer).status_code == 200
    r = client.post(f"/assets/{asset_id(client, viewer, 'LD-09')}/meter", headers=viewer, json={"hours": 7000})
    assert r.status_code == 403


def test_parca_filtreleri(client, manager):
    stock = client.get("/parts", params={"status": "in_stock"}, headers=manager).json()
    assert {p["serial_no"] for p in stock} >= {"BS18-2290", "TR25-0107"}
    crit = client.get("/parts", params={"band": "critical"}, headers=manager).json()
    assert all(p["band"] == "critical" for p in crit)


def test_gecersiz_girdi_turkce_alan_listesi(client, tech):
    r = client.post(f"/parts/{part_id(client, tech, 'MX29-0412')}/remove", headers=tech, json={"next_status": "yok"})
    assert r.status_code == 422
    body = r.json()
    assert body["detail"] == "Girilen bilgiler geçersiz"
    assert {f["field"] for f in body["fields"]} >= {"reason", "next_status"}
