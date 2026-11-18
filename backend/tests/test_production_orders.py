"""Rota, üretim emri ve işlem süresi: emre kopyalama, başla / durdur kuralları, tamamlama, rapor."""

import psycopg

PRODUCT = "51111111-0000-0000-0000-000000000008"    # KB-BOOM-450 (ürün)
FILTER = "51111111-0000-0000-0000-000000000011"     # VOE-11110683 (ağacı olmayan kalem)
URL = "/production"
ROUTE = [{"name": "Kesim", "planned_minutes": 30}, {"name": "Kaynak", "planned_minutes": "45.5"}, {"name": "Boya"}]


def backdate(settings, op_id: str, minutes: int) -> None:
    """İşlemin açık zaman kayıtlarını geriye çeker: süre hesabını denemek için."""
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("update public.production_time_logs set started_at = now() - make_interval(mins => %s) "
                     "where op_id = %s and ended_at is null", [minutes, op_id])
        conn.commit()


def ops(order: dict) -> dict:
    return {o["name"]: o for o in order["operations"]}


def test_rota_kaydedilir(client, manager, tech, other):
    bom = client.post(f"{URL}/boms", headers=manager, json={"part_id": PRODUCT}).json()["id"]
    assert client.get(f"{URL}/routes/{bom}", headers=tech).json() == []
    assert client.put(f"{URL}/routes/{bom}", headers=tech, json={"operations": ROUTE}).status_code == 403
    assert client.put(f"{URL}/routes/{bom}", headers=other, json={"operations": ROUTE}).status_code == 404
    dup = {"operations": [{"name": "Kesim"}, {"name": "kesim "}]}
    assert client.put(f"{URL}/routes/{bom}", headers=manager, json=dup).status_code == 422
    assert client.put(f"{URL}/routes/{bom}", headers=manager, json={"operations": [{"name": "Kesim", "planned_minutes": 0}]}).status_code == 422

    # Rota boşken emir açılmaz
    r = client.post(f"{URL}/orders", headers=manager, json={"part_id": PRODUCT, "qty": 1})
    assert r.status_code == 422 and "rota" in r.json()["detail"].lower()

    r = client.put(f"{URL}/routes/{bom}", headers=manager, json={"operations": ROUTE})
    assert r.status_code == 200, r.text
    assert [(o["seq"], o["name"], o["planned_minutes"] and float(o["planned_minutes"])) for o in r.json()] == [
        (1, "Kesim", 30), (2, "Kaynak", 45.5), (3, "Boya", None)]
    # Liste tümden değişir
    r = client.put(f"{URL}/routes/{bom}", headers=manager, json={"operations": ROUTE[:2]})
    assert [o["name"] for o in r.json()] == ["Kesim", "Kaynak"]
    client.put(f"{URL}/routes/{bom}", headers=manager, json={"operations": ROUTE})


def test_emir_rotadan_acilir(client, manager, tech, other):
    assert client.post(f"{URL}/orders", headers=tech, json={"part_id": PRODUCT, "qty": 4}).status_code == 403
    assert client.post(f"{URL}/orders", headers=manager, json={"part_id": FILTER, "qty": 4}).status_code == 404
    assert client.post(f"{URL}/orders", headers=manager, json={"part_id": PRODUCT, "qty": 0}).status_code == 422
    r = client.post(f"{URL}/orders", headers=manager, json={"part_id": PRODUCT, "qty": 4, "due_at": "2020-01-01"})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["number"].startswith("UE-") and o["number"].endswith("-0001") and o["status"] == "open" and o["late"]
    # Planlanan süre = birim süre × miktar; planı olmayan işlem boş kalır
    assert [(x["name"], x["planned_minutes"] and float(x["planned_minutes"])) for x in o["operations"]] == [
        ("Kesim", 120), ("Kaynak", 182), ("Boya", None)]
    assert float(o["planned_minutes"]) == 302 and o["op_count"] == 3 and o["ops_done"] == 0

    # Rota sonradan değişse de açılmış emir değişmez
    bom = client.get(f"{URL}/boms", headers=manager).json()[0]["id"]
    client.put(f"{URL}/routes/{bom}", headers=manager, json={"operations": [{"name": "Montaj", "planned_minutes": 10}]})
    assert [x["name"] for x in client.get(f"{URL}/orders/{o['id']}", headers=tech).json()["operations"]] == ["Kesim", "Kaynak", "Boya"]
    client.put(f"{URL}/routes/{bom}", headers=manager, json={"operations": ROUTE})

    assert client.get(f"{URL}/orders", headers=other).json() == []
    assert client.get(f"{URL}/orders/{o['id']}", headers=other).status_code == 404
    op = o["operations"][0]["id"]
    assert client.post(f"{URL}/orders/{o['id']}/ops/{op}/start", headers=other).status_code == 404


def test_basla_durdur_bitir(client, manager, tech, settings):
    o = client.get(f"{URL}/orders", headers=tech).json()[0]
    oid = o["id"]
    op = {k: v["id"] for k, v in ops(client.get(f"{URL}/orders/{oid}", headers=tech).json()).items()}
    start = lambda name, h: client.post(f"{URL}/orders/{oid}/ops/{op[name]}/start", headers=h)  # noqa: E731
    stop = lambda name, h, done=False: client.post(f"{URL}/orders/{oid}/ops/{op[name]}/stop", headers=h, json={"done": done})  # noqa: E731

    # Süren kaydı olmayan durduramaz
    assert stop("Kesim", tech).status_code == 422
    r = start("Kesim", tech)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "in_progress" and d["started_at"] and d["running"] == 1
    assert ops(d)["Kesim"]["mine"] and len(ops(d)["Kesim"]["running_by"]) == 1
    # Bir kişi aynı anda tek işlemde çalışır
    r = start("Kaynak", tech)
    assert r.status_code == 422 and "Kesim" in r.json()["detail"]
    # Aynı işlemde ikinci kişi çalışabilir; yöneticinin görünümünde kayıt "benim" değildir
    assert not ops(client.get(f"{URL}/orders/{oid}", headers=manager).json())["Kesim"]["mine"]
    assert start("Kesim", manager).status_code == 200

    backdate(settings, op["Kesim"], 20)
    d = stop("Kesim", tech).json()
    kesim = ops(d)["Kesim"]
    # Teknisyen durdu (20 dk), yönetici sürüyor (20 dk ve artıyor)
    assert not kesim["mine"] and len(kesim["running_by"]) == 1 and 39.9 <= float(kesim["actual_minutes"]) <= 41
    assert kesim["done_at"] is None

    # Bitir: süren herkesin kaydı kapanır
    d = stop("Kesim", tech, done=True).json()
    kesim = ops(d)["Kesim"]
    assert kesim["done_at"] and kesim["running_by"] == [] and d["ops_done"] == 1 and d["running"] == 0
    assert start("Kesim", tech).status_code == 422 and stop("Kesim", tech, done=True).status_code == 422
    assert len(d["logs"]) == 2 and all(l["ended_at"] for l in d["logs"])

    # Bitmemiş işlem varken emir tamamlanmaz
    assert client.post(f"{URL}/orders/{oid}/finish", headers=tech, json={"good_qty": 4}).status_code == 422
    assert start("Kaynak", tech).status_code == 200
    backdate(settings, op["Kaynak"], 200)
    assert stop("Kaynak", tech, done=True).status_code == 200
    # Süre tutulmadan da bitti işaretlenir
    assert stop("Boya", tech, done=True).status_code == 200
    assert client.post(f"{URL}/orders/{oid}/status", headers=tech, json={"status": "cancelled"}).status_code == 403
    d = client.post(f"{URL}/orders/{oid}/finish", headers=tech, json={"good_qty": 4}).json()
    assert d["status"] == "done" and d["completed_at"] and not d["late"] and d["ops_done"] == 3
    assert 239.9 <= float(d["actual_minutes"]) <= 242
    assert client.post(f"{URL}/orders/{oid}/status", headers=manager, json={"status": "cancelled"}).status_code == 422


def test_iptal_ve_rapor(client, manager, tech, settings):
    o = client.post(f"{URL}/orders", headers=manager, json={"part_id": PRODUCT, "qty": 1}).json()
    assert o["number"].endswith("-0002")
    op = o["operations"][0]["id"]
    assert client.post(f"{URL}/orders/{o['id']}/ops/{op}/start", headers=tech).status_code == 200
    backdate(settings, op, 500)
    # İptal süren kaydı kapatır; kişi yeni işe başlayabilir
    d = client.post(f"{URL}/orders/{o['id']}/status", headers=manager, json={"status": "cancelled"}).json()
    assert d["status"] == "cancelled" and d["running"] == 0
    assert client.post(f"{URL}/orders/{o['id']}/ops/{op}/start", headers=tech).status_code == 422

    assert [x["status"] for x in client.get(f"{URL}/orders", headers=tech).json()] == ["done", "cancelled"]
    assert client.get(f"{URL}/orders", headers=tech, params={"open_only": True}).json() == []

    # Rapor: biten işlemler; iptal edilen emir sayılmaz
    rows = {r["name"]: r for r in client.get(f"{URL}/reports/operations", headers=tech).json()}
    assert set(rows) == {"Kesim", "Kaynak", "Boya"}
    assert float(rows["Kesim"]["planned_minutes"]) == 120 and 39.9 <= float(rows["Kesim"]["actual_minutes"]) <= 41
    assert float(rows["Kaynak"]["planned_minutes"]) == 182 and 199.9 <= float(rows["Kaynak"]["actual_minutes"]) <= 201
    assert rows["Boya"]["planned_minutes"] is None and float(rows["Boya"]["actual_planned_minutes"]) == 0
    assert rows["Kaynak"]["order_count"] == 1
