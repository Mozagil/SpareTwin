"""Veritabanı erişimi.

Altın kural: Kullanıcı adına yapılan HER sorgu `user_tx()` içinden geçer.
`user_tx` işlemi kısıtlı `sparetwin_app` rolüne geçirir ve kullanıcının
kimliğini oturuma yazar; böylece RLS kuralları her sorguda uygulanır.
`owner_tx()` yalnızca migrasyon, CLI ve sistem işleri içindir.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def init_pool(url: str, min_size: int = 1, max_size: int = 10) -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            url,
            min_size=min_size,
            max_size=max_size,
            # prepare_threshold=None: sunucu tarafı hazır sorgu (prepared statement) kullanma.
            # Aksi halde API çalışırken şema değişirse (make reset, migrasyon) önbellekteki
            # planlar eskir ve "cached plan must not change result type" hatası alınır.
            kwargs={"row_factory": dict_row, "autocommit": False, "prepare_threshold": None},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("Veritabanı havuzu başlatılmadı")
    return _pool


@contextmanager
def user_tx(user_id: UUID | None) -> Iterator[psycopg.Connection]:
    """Kullanıcı adına tek bir işlem (transaction). Hata olursa geri alınır."""
    with pool().connection() as conn:
        with conn.transaction():
            conn.execute("set local role sparetwin_app")
            conn.execute(
                "select set_config('app.user_id', %s, true)",
                [str(user_id) if user_id else ""],
            )
            yield conn


@contextmanager
def owner_tx() -> Iterator[psycopg.Connection]:
    """Sahip yetkisiyle işlem. RLS uygulanmaz; yalnızca sistem işleri için."""
    with pool().connection() as conn:
        with conn.transaction():
            yield conn


# ---------- Postgres hatalarını HTTP'ye çevirme ----------
# Veritabanı fonksiyonları Türkçe, kullanıcıya gösterilebilir mesajlar üretir.
SQLSTATE_TO_HTTP: dict[str, int] = {
    "P0002": 404,  # bulunamadı (fonksiyonlarımız)
    "22023": 422,  # geçersiz parametre / iş kuralı ihlali
    "23505": 409,  # benzersizlik / dolu pozisyon
    "23503": 422,  # yabancı anahtar
    "23514": 422,  # check kısıtı
    "22P02": 422,  # geçersiz değer biçimi (ör. enum)
    "42501": 403,  # yetki / RLS
}


def http_status_for(exc: psycopg.Error) -> int | None:
    state = getattr(exc, "sqlstate", None)
    return SQLSTATE_TO_HTTP.get(state or "")


def user_message_for(exc: psycopg.Error) -> str:
    state = getattr(exc, "sqlstate", None)
    diag = getattr(exc, "diag", None)
    primary = diag.message_primary if diag else None
    if state == "42501" and primary and "row-level security" in primary:
        return "Bu işlem için yetkiniz yok"
    if state == "23505" and primary and "duplicate key" in primary:
        return "Bu kayıt zaten var"
    if state == "23503":
        return "İlişkili kayıt bulunamadı"
    if state == "22P02":
        return "Geçersiz değer"
    return primary or "Veritabanı hatası"
