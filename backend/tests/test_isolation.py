"""Firma izolasyonu: SaaS'ın en kritik garantisi.

Hem API seviyesinde hem de doğrudan veritabanı seviyesinde (API'de filtre
unutulmuş gibi) test edilir.
"""

import psycopg
import pytest

from conftest import OTHER_TENANT, asset_id, part_id
from sparetwin.db import user_tx


def test_baska_firma_kullanicisi_demo_makinelerini_gormez(client, other):
    codes = [a["code"] for a in client.get("/assets", headers=other).json()]
    assert codes == ["BF-01"]


def test_baska_firma_demo_kaydina_dogrudan_erisemez(client, manager, other):
    ld07 = asset_id(client, manager, "LD-07")
    tire = part_id(client, manager, "MX29-0412")
    assert client.get(f"/assets/{ld07}", headers=other).status_code == 404
    assert client.get(f"/parts/{tire}", headers=other).status_code == 404
    assert client.get(f"/parts/{tire}/events", headers=other).json() == []
    r = client.post(f"/parts/{tire}/remove", headers=other, json={"reason": "worn_out"})
    assert r.status_code == 404


def test_uye_olunmayan_firma_basligi_reddedilir(client, manager):
    r = client.get("/assets", headers={**manager, "X-Tenant-Id": OTHER_TENANT})
    assert r.status_code == 403


def test_rls_api_filtresi_olmasa_bile_veriyi_korur(client, other):
    """API'de 'where tenant_id = ...' unutulmuş gibi doğrudan sorgu."""
    me = client.get("/auth/me", headers=other).json()["id"]
    with user_tx(me) as conn:
        assert conn.execute("select count(*) as n from public.assets").fetchone()["n"] == 1
        assert conn.execute("select count(*) as n from public.part_items").fetchone()["n"] == 0
        assert conn.execute("select count(*) as n from public.v_asset_health").fetchone()["n"] == 1
        # Ortak kütüphane herkese açık
        assert conn.execute("select count(*) as n from public.part_categories").fetchone()["n"] >= 6


def test_api_rolu_parola_ozetini_okuyamaz(client, manager):
    me = client.get("/auth/me", headers=manager).json()["id"]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with user_tx(me) as conn:
            conn.execute("select password_hash from public.app_users")


def test_api_rolu_token_tablosunu_okuyamaz(client, manager):
    me = client.get("/auth/me", headers=manager).json()["id"]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with user_tx(me) as conn:
            conn.execute("select * from public.refresh_tokens")


def test_yasam_dongusu_defteri_degistirilemez(client, manager):
    me = client.get("/auth/me", headers=manager).json()["id"]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with user_tx(me) as conn:
            conn.execute("update public.part_events set cost = 1")


def test_kimliksiz_oturum_hicbir_sey_gormez(client):
    with user_tx(None) as conn:
        assert conn.execute("select count(*) as n from public.assets").fetchone()["n"] == 0
        assert conn.execute("select count(*) as n from public.tenants").fetchone()["n"] == 0
