"""Basit ve öngörülebilir migrasyon çalıştırıcı.

db/migrations/*.sql dosyalarını ad sırasıyla, her biri kendi işleminde
uygular ve app_meta.schema_migrations tablosuna kaydeder. Aynı anda iki
API kopyası açılırsa danışma kilidi (advisory lock) çakışmayı önler.
Müşteri sunucusunda güncelleme = yeni imajı çalıştırmak; eksik migrasyonlar
açılışta kendiliğinden uygulanır.
"""

import hashlib
import logging
from pathlib import Path

import psycopg

log = logging.getLogger("sparetwin.migrate")
LOCK_ID = 7_102_026


def _files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.sql") if p.is_file())


def migrate(conn: psycopg.Connection, directory: Path) -> list[str]:
    """Uygulanmamış migrasyonları uygular, uygulananların adlarını döner."""
    applied_now: list[str] = []
    conn.autocommit = True
    conn.execute("select pg_advisory_lock(%s)", [LOCK_ID])
    try:
        conn.execute("create schema if not exists app_meta")
        conn.execute(
            """create table if not exists app_meta.schema_migrations (
                 version    text primary key,
                 checksum   text not null,
                 applied_at timestamptz not null default now())"""
        )
        done = {
            r[0]: r[1]
            for r in conn.execute("select version, checksum from app_meta.schema_migrations").fetchall()
        }
        for path in _files(directory):
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if path.name in done:
                if done[path.name] != checksum:
                    log.warning(
                        "%s uygulandıktan sonra değiştirilmiş. Uygulanmış migrasyonu "
                        "düzenlemek yerine yeni bir migrasyon dosyası ekleyin.", path.name
                    )
                continue
            log.info("Migrasyon uygulanıyor: %s", path.name)
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "insert into app_meta.schema_migrations (version, checksum) values (%s, %s)",
                    [path.name, checksum],
                )
            applied_now.append(path.name)
    finally:
        conn.execute("select pg_advisory_unlock(%s)", [LOCK_ID])
        conn.autocommit = False
    return applied_now


def run(database_url: str, directory: Path) -> list[str]:
    with psycopg.connect(database_url) as conn:
        return migrate(conn, directory)
