from conftest import DEMO_PW, login


def test_giris_basarili_ve_firmalar_doner(client):
    body = login(client, "yonetici@demo.sparetwin.dev")
    assert body["token_type"] == "bearer"
    assert body["user"]["memberships"][0]["tenant_slug"] == "demo"
    assert body["user"]["memberships"][0]["role"] == "owner"


def test_yanlis_parola_ve_olmayan_eposta_ayni_mesaji_verir(client):
    a = client.post("/auth/login", json={"email": "yonetici@demo.sparetwin.dev", "password": "yanlis"})
    b = client.post("/auth/login", json={"email": "yok@demo.sparetwin.dev", "password": "yanlis"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_eposta_buyuk_kucuk_harf_duyarsiz(client):
    assert client.post("/auth/login", json={"email": "YONETICI@demo.sparetwin.dev", "password": DEMO_PW}).status_code == 200


def test_tokensiz_ve_bozuk_token_reddedilir(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer bozuk"}).status_code == 401
    assert client.get("/assets").status_code == 401


def test_refresh_doner_ve_eski_token_tekrar_kullanilinca_tum_oturumlar_kapanir(client):
    first = login(client, "teknisyen@demo.sparetwin.dev")
    r1 = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r1.status_code == 200
    second = r1.json()
    assert second["refresh_token"] != first["refresh_token"]

    # Eski token tekrar kullanıldı: çalınmış olabilir, reddedilir...
    assert client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    # ...ve o kullanıcının yeni token'ı da iptal edilmiştir.
    assert client.post("/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 401


def test_cikis_yapinca_refresh_gecersiz(client):
    t = login(client, "teknisyen@demo.sparetwin.dev")
    assert client.post("/auth/logout", json={"refresh_token": t["refresh_token"]}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401


def test_parola_degistirme(client):
    t = login(client, "teknisyen@demo.sparetwin.dev")
    h = {"Authorization": f"Bearer {t['access_token']}"}
    bad = client.post("/auth/password", headers=h, json={"current_password": "yanlis", "new_password": "yeni-parola-123"})
    assert bad.status_code == 400
    short = client.post("/auth/password", headers=h, json={"current_password": DEMO_PW, "new_password": "kisa"})
    assert short.status_code == 422
    ok = client.post("/auth/password", headers=h, json={"current_password": DEMO_PW, "new_password": "yeni-parola-123"})
    assert ok.status_code == 204
    # Parola değişince açık oturumların yenileme token'ı geçersiz
    assert client.post("/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401
    login(client, "teknisyen@demo.sparetwin.dev", "yeni-parola-123")
    # geri al (diğer testler demo parolasını kullanıyor)
    t2 = login(client, "teknisyen@demo.sparetwin.dev", "yeni-parola-123")
    client.post(
        "/auth/password",
        headers={"Authorization": f"Bearer {t2['access_token']}"},
        json={"current_password": "yeni-parola-123", "new_password": DEMO_PW},
    )
