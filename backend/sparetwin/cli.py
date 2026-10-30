"""SpareTwin yönetim komutları.

    python -m sparetwin.cli migrate
    python -m sparetwin.cli wait-db
    python -m sparetwin.cli seed-demo
    python -m sparetwin.cli reset-dev            # yalnızca ENV=dev/test
    python -m sparetwin.cli create-tenant --name "Acme Liman A.Ş." --slug acme
    python -m sparetwin.cli create-user --email ali@acme.com --name "Ali Yılmaz" \\
                                        --tenant acme --role owner
"""

import argparse
import getpass
import logging
import sys

import psycopg

from .config import Settings, get_settings
from .migrate import run as run_migrations
from .security import MIN_PASSWORD_LEN, hash_password

DEMO_TENANT = "11111111-1111-1111-1111-111111111111"
DEMO_USERS = [
    # (e-posta, ad, rol)
    ("yonetici@demo.sparetwin.dev", "Demo Yönetici", "owner"),
    ("teknisyen@demo.sparetwin.dev", "Demo Teknisyen", "technician"),
]
DEMO_PASSWORD = "demo-parola-2026"


def cmd_migrate(s: Settings) -> None:
    applied = run_migrations(s.database_url, s.migrations_dir)
    print("Uygulanan migrasyon:", ", ".join(applied) if applied else "yok, şema güncel")


def cmd_wait_db(s: Settings, timeout: int = 60) -> None:
    """Veritabanı bağlantı kabul edene kadar bekler (container yeni açıldıysa)."""
    import time

    deadline = time.monotonic() + timeout
    while True:
        try:
            with psycopg.connect(s.database_url, connect_timeout=3) as conn:
                conn.execute("select 1")
            print("Veritabanı hazır.")
            return
        except psycopg.OperationalError as e:
            if time.monotonic() > deadline:
                sys.exit(f"Veritabanına {timeout} sn içinde bağlanılamadı: {e}")
            time.sleep(2)


def cmd_reset_dev(s: Settings) -> None:
    if s.env not in ("dev", "test"):
        sys.exit("reset-dev yalnızca ENV=dev veya ENV=test iken çalışır")
    with psycopg.connect(s.database_url, autocommit=True) as conn:
        conn.execute("drop schema if exists app_meta cascade")
        conn.execute("drop schema if exists app cascade")
        conn.execute("drop schema if exists public cascade")
        conn.execute("create schema public")
    print("Şema silindi.")
    cmd_migrate(s)


def ensure_user(conn: psycopg.Connection, email: str, name: str, password: str) -> str:
    row = conn.execute(
        """insert into public.app_users (email, password_hash, full_name)
           values (%s, %s, %s)
           on conflict (lower(email)) do update set full_name = excluded.full_name
           returning id""",
        [email, hash_password(password), name],
    ).fetchone()
    return str(row[0])


def cmd_seed_demo(s: Settings, password: str | None) -> None:
    sql = (s.seed_dir / "demo.sql").read_text(encoding="utf-8")
    pw = password or DEMO_PASSWORD
    with psycopg.connect(s.database_url) as conn:
        exists = conn.execute("select 1 from public.tenants where id = %s", [DEMO_TENANT]).fetchone()
        if exists:
            print("Demo firma zaten var, veri yüklenmedi.")
        else:
            conn.execute(sql)
        for email, name, role in DEMO_USERS:
            uid = ensure_user(conn, email, name, pw)
            conn.execute(
                """insert into public.memberships (tenant_id, user_id, role) values (%s, %s, %s)
                   on conflict (tenant_id, user_id) do update set role = excluded.role""",
                [DEMO_TENANT, uid, role],
            )
        conn.commit()
    print("Demo veri hazır. Giriş bilgileri (yalnızca geliştirme):")
    for email, _, role in DEMO_USERS:
        print(f"  {email}  /  {pw}   ({role})")


def cmd_create_tenant(s: Settings, name: str, slug: str) -> None:
    with psycopg.connect(s.database_url) as conn:
        row = conn.execute(
            "insert into public.tenants (name, slug) values (%s, %s) returning id", [name, slug]
        ).fetchone()
        conn.commit()
    print(f"Firma oluşturuldu: {name} ({slug}) id={row[0]}")


def cmd_create_user(s: Settings, email: str, name: str, tenant: str | None, role: str) -> None:
    pw = getpass.getpass("Parola: ")
    if len(pw) < MIN_PASSWORD_LEN:
        sys.exit(f"Parola en az {MIN_PASSWORD_LEN} karakter olmalı")
    if pw != getpass.getpass("Parola (tekrar): "):
        sys.exit("Parolalar eşleşmiyor")
    with psycopg.connect(s.database_url) as conn:
        uid = ensure_user(conn, email, name, pw)
        if tenant:
            t = conn.execute(
                "select id from public.tenants where slug = %s or id::text = %s", [tenant, tenant]
            ).fetchone()
            if not t:
                sys.exit(f"Firma bulunamadı: {tenant}")
            conn.execute(
                """insert into public.memberships (tenant_id, user_id, role) values (%s, %s, %s)
                   on conflict (tenant_id, user_id) do update set role = excluded.role""",
                [t[0], uid, role],
            )
        conn.commit()
    print(f"Kullanıcı hazır: {email} id={uid}")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="sparetwin")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="Eksik migrasyonları uygula")
    sub.add_parser("wait-db", help="Veritabanı hazır olana kadar bekle")
    sub.add_parser("reset-dev", help="Şemayı silip yeniden kur (yalnızca geliştirme)")
    sd = sub.add_parser("seed-demo", help="Demo firma, makineler ve kullanıcılar")
    sd.add_argument("--password", help="Demo kullanıcı parolası")
    ct = sub.add_parser("create-tenant", help="Yeni firma")
    ct.add_argument("--name", required=True)
    ct.add_argument("--slug", required=True)
    cu = sub.add_parser("create-user", help="Yeni kullanıcı (parola sorulur)")
    cu.add_argument("--email", required=True)
    cu.add_argument("--name", required=True)
    cu.add_argument("--tenant", help="Firma slug veya id")
    cu.add_argument("--role", default="viewer",
                    choices=["owner", "admin", "manager", "technician", "viewer"])
    a = p.parse_args(argv)

    s = get_settings()
    match a.cmd:
        case "migrate":
            cmd_migrate(s)
        case "wait-db":
            cmd_wait_db(s)
        case "reset-dev":
            cmd_reset_dev(s)
        case "seed-demo":
            cmd_seed_demo(s, a.password)
        case "create-tenant":
            cmd_create_tenant(s, a.name, a.slug)
        case "create-user":
            cmd_create_user(s, a.email, a.name, a.tenant, a.role)


if __name__ == "__main__":
    main()
