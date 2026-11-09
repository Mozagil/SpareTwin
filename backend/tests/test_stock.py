"""Depo ve stok: sarf malzemeleri, hareketler, transfer, sayım, kurallar."""

import psycopg
import pytest

from conftest import asset_id, auth

FILTER = "51111111-0000-0000-0000-000000000011"   # L220H hidrolik filtresi (adet, kritik 6)
OIL = "51111111-0000-0000-0000-000000000012"      # Motor yağı (litre, kritik 200)
SOMA = "21111111-0000-0000-0000-000000000002"
AMBARLI = "21111111-0000-0000-0000-000000000001"


def level(client, h, part):
    return next(s for s in client.get("/stock", headers=h).json() if s["part_id"] == part)


def move(client, h, **body):
    return client.post("/stock/movements", headers=h, json=body)


def test_stok_listesi_sarf_ve_seri_numarali_bir_arada(client, manager):
    rows = client.get("/stock", headers=manager).json()
    names = {r["name"]: r for r in rows}
    oil = names["Motor yağı 15W-40"]
    assert float(oil["qty"]) == 360 and oil["unit"] == "litre" and oil["below_min"] is False
    assert {s["site_id"]: float(s["qty"]) for s in oil["sites"]} == {SOMA: 280, AMBARLI: 80}
    assert round(float(oil["avg_cost"]), 3) == 4.108  # (400×4,05 + 120×4,30) / 520
    assert float(oil["used_90d"]) == 160
    assert names["L220H hidrolik filtresi"]["below_min"] is True
    assert float(names["29.5R25 L-4 radyal"]["qty"]) == 1 and names["29.5R25 L-4 radyal"]["is_serialized"]
    assert rows[0]["below_min"] is True  # kritikler önce
    assert all(r["below_min"] for r in client.get("/stock", headers=manager, params={"below": True}).json())


def test_giris_cikis_ve_eksi_stok_yok(client, tech):
    ld07 = asset_id(client, tech, "LD-07")
    r = move(client, tech, part_id=FILTER, site_id=SOMA, kind="in", qty=10, unit_cost=90, ref="IRS-1")
    assert r.status_code == 201 and float(r.json()["level"]) == 14
    r = move(client, tech, part_id=FILTER, site_id=SOMA, kind="out", qty=3, asset_id=ld07, reason="periyodik bakım")
    assert r.status_code == 201 and float(r.json()["qty"]) == -3 and float(r.json()["level"]) == 11
    # Çıkışın maliyeti ağırlıklı ortalama: (12×82 + 10×90) / 22
    assert round(float(r.json()["unit_cost"]), 2) == 85.64
    r = move(client, tech, part_id=FILTER, site_id=SOMA, kind="out", qty=50)
    assert r.status_code == 422 and "Stokta yeterli yok (depoda 11, istenen 50)" in r.json()["detail"]
    assert move(client, tech, part_id=FILTER, site_id=AMBARLI, kind="out", qty=1).status_code == 422  # Ambarlı'da yok
    assert move(client, tech, part_id=FILTER, site_id=SOMA, kind="in", qty=0).status_code == 422


def test_sayim_duzeltmesi(client, tech):
    before = float(level(client, tech, OIL)["qty"])
    r = move(client, tech, part_id=OIL, site_id=SOMA, kind="adjust", qty=275, reason="aylık sayım")
    assert r.status_code == 201 and float(r.json()["qty"]) == -5 and float(r.json()["level"]) == 275
    assert float(level(client, tech, OIL)["qty"]) == before - 5
    r = move(client, tech, part_id=OIL, site_id=SOMA, kind="adjust", qty=275)
    assert r.status_code == 422 and "aynı" in r.json()["detail"]


def test_depolar_arasi_transfer(client, tech):
    total = float(level(client, tech, OIL)["qty"])
    r = client.post("/stock/transfer", headers=tech, json={"part_id": OIL, "from_site_id": SOMA, "to_site_id": AMBARLI, "qty": 100})
    assert r.status_code == 201
    sites = {s["site_id"]: float(s["qty"]) for s in level(client, tech, OIL)["sites"]}
    assert sites[AMBARLI] == 180 and float(level(client, tech, OIL)["qty"]) == total  # toplam değişmez
    mv = client.get(f"/stock/{OIL}/movements", headers=tech).json()
    assert [m["kind"] for m in mv[:2]] == ["transfer_in", "transfer_out"] or [m["kind"] for m in mv[:2]] == ["transfer_out", "transfer_in"]
    bad = client.post("/stock/transfer", headers=tech, json={"part_id": OIL, "from_site_id": SOMA, "to_site_id": SOMA, "qty": 1})
    assert bad.status_code == 422
    toomuch = client.post("/stock/transfer", headers=tech, json={"part_id": OIL, "from_site_id": AMBARLI, "to_site_id": SOMA, "qty": 9999})
    assert toomuch.status_code == 422
    assert float(level(client, tech, OIL)["qty"]) == total  # başarısız transfer yarım iz bırakmaz


def test_seri_numarali_kalem_stok_hareketiyle_girilemez_sarf_teslim_alma_ile_girilemez(client, manager):
    tire_cat = next(r["part_id"] for r in client.get("/stock", headers=manager).json() if r["name"] == "29.5R25 L-4 radyal")
    r = move(client, manager, part_id=tire_cat, site_id=SOMA, kind="in", qty=1)
    assert r.status_code == 422 and "Parça teslim al" in r.json()["detail"]
    r = client.post("/parts", headers=manager, json={"part_id": FILTER, "items": [{}]})
    assert r.status_code == 422 and "Stok sayfasından" in r.json()["detail"]


def test_firma_izolasyonu_ve_yetki(client, manager, other):
    assert all(r["name"] != "Motor yağı 15W-40" for r in client.get("/stock", headers=other).json())
    assert move(client, other, part_id=OIL, site_id=SOMA, kind="out", qty=1).status_code == 404
    # Başka firmanın makinesine çıkış yapılamaz
    bf = asset_id(client, other, "BF-01")
    r = move(client, manager, part_id=OIL, site_id=SOMA, kind="out", qty=1, asset_id=bf)
    assert r.status_code == 404 and "Makine bulunamadı" in r.json()["detail"]
    from sparetwin.db import owner_tx
    with owner_tx() as conn:
        conn.execute("""insert into public.app_users (email, password_hash, full_name)
                        select 'izleyici3@demo.sparetwin.dev', password_hash, 'İzleyici' from public.app_users
                         where email = 'yonetici@demo.sparetwin.dev'""")
        conn.execute("""insert into public.memberships (tenant_id, user_id, role) select '11111111-1111-1111-1111-111111111111', id, 'viewer'
                          from public.app_users where email = 'izleyici3@demo.sparetwin.dev'""")
    viewer = auth(client, "izleyici3@demo.sparetwin.dev")
    assert client.get("/stock", headers=viewer).status_code == 200
    assert move(client, viewer, part_id=OIL, site_id=SOMA, kind="in", qty=1).status_code == 403


def test_defter_degistirilemez(client, manager):
    from sparetwin.db import user_tx
    me = client.get("/auth/me", headers=manager).json()["id"]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with user_tx(me) as conn:
            conn.execute("update public.stock_movements set qty = 1000")


def test_stok_uyarisi_bildirimi_ve_katalog(client, manager):
    titles = [i["title"] for i in client.get("/notifications", headers=manager).json()["items"] if i["kind"] == "stock_low"]
    assert "L220H kaldırma silindiri keçe takımı stoğu düşük" in titles
    keçe = next(i for i in client.get("/notifications", headers=manager).json()["items"] if "keçe" in i["title"])
    assert keçe["body"] == "Depoda 1 takım, kritik seviye 2, siparişte 1 takım"  # demo siparişi SA-…-0001
    cat = {c["name"]: c for c in client.get("/catalog/parts", headers=manager).json()}
    assert float(cat["Motor yağı 15W-40"]["in_stock"]) > 0 and cat["Motor yağı 15W-40"]["unit"] == "litre"
    assert cat["Motor yağı 15W-40"]["is_serialized"] is False
