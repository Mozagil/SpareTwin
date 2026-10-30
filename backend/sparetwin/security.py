"""Parola özeti, erişim token'ı (JWT) ve yenileme token'ı yardımcıları."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import Settings

_hasher = PasswordHasher()  # argon2id, kütüphanenin güvenli varsayılanları
# Kullanıcı yoksa da aynı süreyi harcamak için (zamanlama ile e-posta tahmini engellenir)
_DUMMY_HASH = _hasher.hash("sparetwin-dummy-password")

MIN_PASSWORD_LEN = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(settings: Settings, user_id: UUID) -> tuple[str, int]:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.access_token_minutes)
    token = jwt.encode(
        {"sub": str(user_id), "type": "access", "iat": now, "exp": exp},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, settings.access_token_minutes * 60


def decode_access_token(settings: Settings, token: str) -> UUID | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


def new_refresh_token(settings: Settings) -> tuple[str, str, datetime]:
    """(istemciye verilecek token, veritabanına yazılacak özet, son kullanma)"""
    raw = secrets.token_urlsafe(48)
    expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_days)
    return raw, hash_token(raw), expires


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------- Dosya linkleri için kısa ömürlü imza ----------
def create_media_token(settings: Settings, storage_key: str, mime: str, file_name: str | None) -> str:
    exp = datetime.now(UTC) + timedelta(minutes=settings.media_url_minutes)
    return jwt.encode(
        {"k": storage_key, "m": mime, "n": file_name, "type": "media", "exp": exp},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_media_token(settings: Settings, token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("type") == "media" else None
