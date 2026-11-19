"""Faz 2: bakım planları, duruş, toplam sahip olma maliyeti, ayarlar."""

from conftest import asset_id, auth

FILTER = "51111111-0000-0000-0000-000000000011"
SOMA = "21111111-0000-0000-0000-000000000002"
P_LD07 = "81111111-0000-0000-0000-000000000001"   # hidrolik filtre, 500 sa, yaklaşıyor (20 sa)
P_LD09 = "81111111-0000-0000-0000-000000000002"   # yağ, 250 sa, gecikmiş (60 sa)


def plans(client, h, **q):
    return {p["id"]: p for p in client.get("/maintenance/plans", headers=h, params=q).json()}


def stock(client, h, pid):
    return float(next(r for r in client.get("/stock", headers=h).json() if r["part_id"] == pid)["qty"])


# ---------- Bakım ----------
def test_bakim_durumlari(client, manager):
    p = plans(client, manager)
    assert p[P_LD07]["due_status"] == "due_soon" and float(p[P_LD07]["hours_left"]) == 20
    assert p[P_LD09]["due_status"] == "overdue" and float(p[P_LD09]["hours_left"]) == -60
    rs = next(x for x in p.values() if x["asset_code"] == "RS-02")
    assert rs["due_status"] == "overdue" and rs["days_left"] == -20
    assert next(x for x in p.values() if x["asset_code"] == "FL-14")["due_status"] == "ok"
    assert list(p.values())[0]["due_status"] == "overdue"  # gecikmişler önce
    assert p[P_LD07]["materials"][0]["name"] == "L220H hidrolik filtresi"
    titles = [i["title"] for i in client.get("/notifications", headers=manager).json()["items"] if i["kind"] == "maintenance_due"]
    assert {"LD-09: Motor yağı değişimi gecikti", "RS-02: Genel periyodik bakım gecikti",
            "LD-07: Hidrolik filtre değişimi yaklaşıyor"} <= set(titles)


def test_bakim_yapildi_plan_sifirlanir_malzeme_stoktan_duser(client, tech):
    before = stock(client, tech, FILTER)
    r = client.post(f"/maintenance/plans/{P_LD07}/complete", headers=tech,
                    json={"labor_cost": 380, "notes": "Filtreler değişti", "site_id": SOMA})
    assert r.status_code == 200, r.text
    assert float(r.json()["asset_hours"]) == 12480 and len(r.json()["consumed"]) == 1
    p = plans(client, tech)[P_LD07]
    assert p["due_status"] == "ok" and float(p["hours_left"]) == 500
    assert stock(client, tech, FILTER) == before - 2
    mv = client.get(f"/stock/{FILTER}/movements", headers=tech).json()[0]
    assert mv["asset_code"] == "LD-07" and mv["reason"] == "bakım"
    rec = client.get("/maintenance/records", headers=tech, params={"asset_id": asset_id(client, tech, "LD-07")}).json()[0]
    assert rec["title"] == "Hidrolik filtre değişimi" and float(rec["labor_cost"]) == 380


def test_malzeme_yoksa_bakim_kaydi_yazilmaz(client, manager, tech):
    ld07 = asset_id(client, manager, "LD-07")
    r = client.post("/maintenance/plans", headers=manager, json={
        "asset_id": ld07, "name": "Test: çok filtre", "interval_hours": 100, "materials": [{"part_id": FILTER, "qty": 999}]})
    assert r.status_code == 201
    pid = r.json()["id"]
    n_before = len(client.get("/maintenance/records", headers=tech).json())
    r = client.post(f"/maintenance/plans/{pid}/complete", headers=tech, json={"site_id": SOMA})
    assert r.status_code == 422 and "Stokta yeterli yok" in r.json()["detail"]
    assert len(client.get("/maintenance/records", headers=tech).json()) == n_before   # kayıt yok
    # Malzemesiz tamamlanabilir (malzeme başka yerden geldiyse)
    assert client.post(f"/maintenance/plans/{pid}/complete", headers=tech, json={"consume_materials": False}).status_code == 200


def test_plan_kurallari(client, manager, tech):
    ld07 = asset_id(client, manager, "LD-07")
    assert client.post("/maintenance/plans", headers=manager, json={"asset_id": ld07, "name": "Periyotsuz"}).status_code == 422
    tire_cat = next(r["part_id"] for r in client.get("/stock", headers=manager).json() if r["name"] == "29.5R25 L-4 radyal")
    r = client.post("/maintenance/plans", headers=manager, json={"asset_id": ld07, "name": "Lastik planı", "interval_days": 30,
                                                                  "materials": [{"part_id": tire_cat, "qty": 1}]})
    assert r.status_code == 422 and "sarf" in r.json()["detail"]
    assert client.post("/maintenance/plans", headers=tech, json={"asset_id": ld07, "name": "Yetkisiz", "interval_days": 30}).status_code == 403
    assert client.patch(f"/maintenance/plans/{P_LD09}", headers=manager, json={"active": False}).status_code == 200
    assert plans(client, manager)[P_LD09]["due_status"] == "inactive"
    assert not any("LD-09: Motor yağı" in i["title"] for i in client.get("/notifications", headers=manager).json()["items"])


# ---------- Duruş ----------
def test_durus_baslat_bitir(client, tech, manager):
    open_ = client.get("/downtime", headers=tech, params={"open": True}).json()
    assert [d["asset_code"] for d in open_] == ["FL-14"] and float(open_[0]["hours"]) == 18
    assert any(i["title"] == "FL-14 18 saattir duruşta" for i in client.get("/notifications", headers=manager).json()["items"])
    fl = {a["code"]: a for a in client.get("/assets", headers=tech).json()}
    assert fl["FL-14"]["down_since"] is not None and fl["LD-07"]["down_since"] is None
    r = client.post("/downtime", headers=tech, json={"asset_id": asset_id(client, tech, "FL-14"), "category": "breakdown"})
    assert r.status_code == 409 and "zaten duruşta" in r.json()["detail"]
    r = client.post("/downtime", headers=tech, json={"asset_id": asset_id(client, tech, "LD-07"), "category": "breakdown",
                                                     "description": "Motor arıza lambası"})
    assert r.status_code == 201
    e = client.post(f"/downtime/{r.json()['id']}/end", headers=tech, json={"cost": 650})
    assert e.status_code == 200
    assert client.post(f"/downtime/{r.json()['id']}/end", headers=tech, json={}).status_code == 409
    # Geçmiş bir duruşu sonradan kaydetme
    r = client.post("/downtime", headers=tech, json={"asset_id": asset_id(client, tech, "RS-02"), "category": "tire",
                                                     "started_at": "2026-10-01T08:00:00Z", "ended_at": "2026-10-01T14:30:00Z"})
    assert r.status_code == 201


# ---------- Maliyet ----------
def test_toplam_sahip_olma_maliyeti(client, manager, other):
    d = client.get("/costs/assets", headers=manager, params={"days": 90}).json()
    rows = {r["code"]: r for r in d["rows"]}
    ld09 = rows["LD-09"]  # bu dosyadaki diğer testler LD-09'a stok çıkışı yapmaz
    assert float(ld09["consumables"]) == 571        # 4 filtre × 82 + 60 litre × 4,05
    assert float(ld09["maintenance"]) == 300
    assert float(ld09["hours_worked"]) == 900       # 3 ay × 300 sa
    assert float(ld09["downtime_cost"]) == 1200 and float(ld09["downtime_hours"]) == 14
    assert float(ld09["total"]) == 571 + 300 + 1200 + float(ld09["parts"]) + float(ld09["services"])
    assert float(ld09["cost_per_hour"]) == round(float(ld09["total"]) / 900, 2)
    assert float(d["totals"]["total"]) == sum(float(r["total"]) for r in d["rows"])
    # Tüm zamanlar: 200 gün önceki RS-02 genel bakımı da girer
    all_ = {r["code"]: r for r in client.get("/costs/assets", headers=manager, params={"days": 0}).json()["rows"]}
    assert float(all_["RS-02"]["maintenance"]) == 2400 and float(rows["RS-02"]["maintenance"]) == 0
    one = client.get(f"/costs/assets/{asset_id(client, manager, 'LD-09')}", headers=manager).json()
    assert float(one["consumables"]) == 571
    assert client.get(f"/costs/assets/{asset_id(client, manager, 'LD-07')}", headers=other).status_code == 404
    assert client.get("/costs/assets", headers=other).json()["rows"][0]["code"] == "BF-01"


# ---------- Ayarlar ----------
def test_firma_ayarlari_hesaplari_degistirir(client, manager):
    owner = manager  # demo yöneticisi "owner" rolünde
    s = client.get("/settings", headers=owner).json()
    assert s["inspection_interval_days"] == 30 and s["purchase_horizon_hours"] == 1000 and s["can_edit"]
    tech = auth(client, "teknisyen@demo.sparetwin.dev")
    assert client.put("/settings", headers=tech, json={"inspection_interval_days": 7, "purchase_horizon_hours": 2000}).status_code == 403
    before = next(x for x in client.get("/purchasing/suggestions", headers=owner).json() if x["name"] == "29.5R25 L-4 radyal")
    assert client.put("/settings", headers=owner, json={"inspection_interval_days": 30, "purchase_horizon_hours": 2000}).status_code == 200
    after = next(x for x in client.get("/purchasing/suggestions", headers=owner).json() if x["name"] == "29.5R25 L-4 radyal")
    assert after["upcoming"] == before["upcoming"] + 1   # LD-07 A2-R (~1.292 sa) artık ufukta
    assert any("2.000 saat içinde" in r for r in after["reasons"])


def test_firmaya_ozel_kategori_ve_katalog(client, manager, tech):
    r = client.post("/settings/categories", headers=manager, json={
        "code": "zincir", "name": "Zincir", "is_serialized": True,
        "measurement_profile": [{"metric": "elongation_pct", "label": "Uzama", "unit": "%", "required": True, "max": 10}],
        "required_photo_angles": ["overview"]})
    assert r.status_code == 201, r.text
    assert client.post("/settings/categories", headers=manager, json={"code": "tire", "name": "Lastik 2"}).status_code == 409
    assert client.post("/settings/categories", headers=tech, json={"code": "abc", "name": "Yetkisiz"}).status_code == 403
    lib = next(c for c in client.get("/settings/categories", headers=manager).json() if c["code"] == "tire")
    assert client.patch(f"/settings/categories/{lib['id']}", headers=manager, json={"name": "Değişmez"}).status_code == 403
    # Yeni kategoride katalog kalemi
    r = client.post("/catalog/parts", headers=manager, json={"category_code": "zincir", "name": "Forklift direk zinciri",
                                                             "expected_life_hours": 8000, "list_cost": 650})
    assert r.status_code == 201, r.text


def test_firmaya_ozel_sablon(client, manager, tech):
    lib = next(t for t in client.get("/settings/templates", headers=manager).json() if t["library"] and t["layout"] == "forklift")
    r = client.post("/settings/templates", headers=manager, json={"name": "Forklift + zincir", "copy_from": lib["id"]})
    assert r.status_code == 201
    tid = r.json()["id"]
    t = next(x for x in client.get("/settings/templates", headers=manager).json() if x["id"] == tid)
    assert len(t["positions"]) == len(lib["positions"]) and t["layout"] == "forklift" and not t["library"]
    assert client.post(f"/settings/templates/{tid}/positions", headers=manager,
                       json={"code": "mast-chain-l", "label": "Direk zinciri sol", "category_code": "filter"}).status_code == 201
    t = next(x for x in client.get("/settings/templates", headers=manager).json() if x["id"] == tid)
    assert any(p["code"] == "MAST-CHAIN-L" and not p["on_schematic"] for p in t["positions"])
    assert client.post(f"/settings/templates/{tid}/positions", headers=manager,
                       json={"code": "X1", "label": "Deneme", "category_code": "yok"}).status_code == 422
    assert client.delete(f"/settings/templates/{tid}/positions/MAST-CHAIN-L", headers=manager).status_code == 204
    assert client.post(f"/settings/templates/{lib['id']}/positions", headers=manager,
                       json={"code": "X1", "label": "Deneme", "category_code": "tire"}).status_code == 403
    assert client.post("/settings/templates", headers=tech, json={"name": "Yetkisiz", "copy_from": lib["id"]}).status_code == 403


def test_excel_ile_ilk_kurulum_maliyete_girmez(client, manager):
    from test_import import GOOD, H, post, xlsx
    before = {r["code"]: r for r in client.get("/costs/assets", headers=manager, params={"days": 1}).json()["rows"]}
    assert post(client, manager, xlsx(H, GOOD), dry_run=False).status_code == 200   # LD-30: 4 lastik
    after = {r["code"]: r for r in client.get("/costs/assets", headers=manager, params={"days": 1}).json()["rows"]}
    assert float(after["LD-30"]["parts"]) == 0 and after["LD-30"]["parts_count"] == 0
    assert float(after["LD-07"]["parts"]) == float(before["LD-07"]["parts"])


def test_moduller_kapaninca_bildirimleri_gizlenir(client, manager):
    s = client.get("/settings", headers=manager).json()
    assert s["modules"] == {"tireiq": True, "parts": True, "erp": False}
    kinds = {i["kind"] for i in client.get("/notifications", headers=manager).json()["items"]}
    assert {"rim_ndt", "stock_low"} <= kinds
    body = {"inspection_interval_days": 30, "purchase_horizon_hours": 1000, "modules": {"tireiq": False, "parts": True}}
    assert client.put("/settings", headers=manager, json=body).json()["modules"]["tireiq"] is False
    kinds = {i["kind"] for i in client.get("/notifications", headers=manager).json()["items"]}
    assert not kinds & {"rim_ndt", "rim_missing"} and "stock_low" in kinds
    body["modules"] = {"tireiq": True, "parts": False}
    client.put("/settings", headers=manager, json=body)
    kinds = {i["kind"] for i in client.get("/notifications", headers=manager).json()["items"]}
    assert "rim_ndt" in kinds and not kinds & {"stock_low", "maintenance_due", "downtime_open", "po_late"}
    body["modules"] = {"tireiq": True, "parts": True}
    client.put("/settings", headers=manager, json=body)
