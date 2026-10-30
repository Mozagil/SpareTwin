"""Testler gerçek bir PostgreSQL üzerinde çalışır.

UYARI: TEST_DATABASE_URL'deki veritabanının şeması her test modülünde
silinip yeniden kurulur. Asla canlı veritabanını vermeyin.
Codespace'te docker compose ile gelen 'sparetwin_test' veritabanı kullanılır.
"""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from sparetwin import cli
from sparetwin.config import Settings
from sparetwin.main import create_app
from sparetwin.security import hash_password

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://sparetwin:sparetwin@localhost:5432/sparetwin_test"
)
DEMO_PW = cli.DEMO_PASSWORD
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
OTHER_EMAIL = "yonetici@baska.test"


@pytest.fixture(scope="module")
def settings(tmp_path_factory) -> Settings:
    return Settings(
        env="test",
        database_url=TEST_DB,
        jwt_secret="test-secret-" + "x" * 40,
        storage_backend="local",
        storage_local_dir=tmp_path_factory.mktemp("media"),
        public_base_url="http://testserver",
        migrate_on_start=True,
    )


@pytest.fixture(scope="module")
def client(settings):
    cli.cmd_reset_dev(settings)
    cli.cmd_seed_demo(settings, None)
    _seed_other_tenant(settings)
    with TestClient(create_app(settings)) as c:
        yield c


def _seed_other_tenant(s: Settings) -> None:
    """İzolasyon testleri için ikinci, bağımsız bir firma."""
    with psycopg.connect(s.database_url) as conn:
        conn.execute(
            "insert into public.tenants (id, name, slug) values (%s, 'Başka Firma', 'baska')", [OTHER_TENANT]
        )
        uid = conn.execute(
            "insert into public.app_users (email, password_hash, full_name) values (%s, %s, 'Başka Yönetici') returning id",
            [OTHER_EMAIL, hash_password(DEMO_PW)],
        ).fetchone()[0]
        conn.execute(
            "insert into public.memberships (tenant_id, user_id, role) values (%s, %s, 'owner')", [OTHER_TENANT, uid]
        )
        conn.execute(
            "insert into public.assets (tenant_id, code, meter_hours) values (%s, 'BF-01', 100)", [OTHER_TENANT]
        )
        conn.commit()


def login(client: TestClient, email: str, password: str = DEMO_PW) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def auth(client: TestClient, email: str) -> dict:
    return {"Authorization": f"Bearer {login(client, email)['access_token']}"}


@pytest.fixture(scope="module")
def manager(client):
    return auth(client, "yonetici@demo.sparetwin.dev")


@pytest.fixture(scope="module")
def tech(client):
    return auth(client, "teknisyen@demo.sparetwin.dev")


@pytest.fixture(scope="module")
def other(client):
    return auth(client, OTHER_EMAIL)


def part_id(client: TestClient, headers: dict, serial: str) -> str:
    r = client.get("/parts", params={"q": serial}, headers=headers)
    assert r.status_code == 200, r.text
    rows = [p for p in r.json() if p["serial_no"] == serial]
    assert rows, f"{serial} bulunamadı"
    return rows[0]["id"]


def asset_id(client: TestClient, headers: dict, code: str) -> str:
    return next(a["id"] for a in client.get("/assets", headers=headers).json() if a["code"] == code)
