"""API çalışırken veritabanı sıfırlanırsa (make reset) veya bir migrasyon tipleri
yeniden oluşturursa, açık bağlantılardaki eski sorgu planları hata vermemeli.
Gerçek hata: "cached plan must not change result type" (500).
Düzeltme: sparetwin/db.py içinde prepare_threshold=None."""

import pytest

from conftest import login
from sparetwin import cli
from sparetwin.config import Settings


@pytest.fixture(scope="module")
def settings(settings: Settings) -> Settings:
    # Tek bağlantı: sıfırlamadan sonraki istek, planı önbelleğe almış bağlantıya düşsün
    return settings.model_copy(update={"db_pool_min": 1, "db_pool_max": 1})


def test_api_acikken_tam_sifirlama(client, settings):
    h = {"Authorization": f"Bearer {login(client, 'yonetici@demo.sparetwin.dev')['access_token']}"}
    for _ in range(8):  # psycopg aynı sorguyu 5. kullanımdan sonra sunucuda hazırlar
        assert client.get("/parts", params={"band": "critical"}, headers=h).status_code == 200

    cli.cmd_reset_dev(settings)  # tüm tipler ve görünümler silinip yeniden oluşur
    cli.cmd_seed_demo(settings, None)

    h = {"Authorization": f"Bearer {login(client, 'yonetici@demo.sparetwin.dev')['access_token']}"}
    for _ in range(8):
        r = client.get("/parts", params={"band": "critical"}, headers=h)
        assert r.status_code == 200, r.text
