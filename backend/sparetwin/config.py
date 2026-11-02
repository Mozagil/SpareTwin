"""Uygulama ayarları. Tüm değerler ortam değişkenlerinden (veya .env) okunur.

Aynı imaj hem bulutta (çok firmalı SaaS) hem müşteri sunucusunda (tek firma)
çalışacak şekilde tasarlandı; fark yalnızca bu ayarlardadır.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["dev", "test", "prod"] = "dev"
    deployment_mode: Literal["cloud", "onprem"] = "cloud"

    # Veritabanı: tabloların sahibi olan kullanıcı. API her istekte
    # kısıtlı 'sparetwin_app' rolüne geçer, RLS o role uygulanır.
    database_url: str = "postgresql://sparetwin:sparetwin@localhost:5432/sparetwin"
    db_pool_min: int = 1
    db_pool_max: int = 10
    migrate_on_start: bool = True
    migrations_dir: Path = REPO_ROOT / "db" / "migrations"
    seed_dir: Path = REPO_ROOT / "db" / "seed"

    # Kimlik doğrulama
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 30

    # Frontend farklı bir adresten bağlanırsa izin verilen adresler (virgülle ayrılmış).
    # Frontend /api üzerinden aynı adresten bağlandığında boş kalır.
    cors_origins: str = ""

    # Dosya deposu: 'local' = disk (geliştirme, müşteri sunucusu), 's3' = S3 uyumlu depo
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: Path = Path("/data/media")
    s3_bucket: str = "sparetwin-media"
    s3_endpoint_url: str | None = None
    s3_region: str = "eu-central-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    media_max_bytes: int = 15 * 1024 * 1024
    media_url_minutes: int = 10

    # Dışarıdan erişilen taban adres; yerel depoda imzalı dosya linki için
    public_base_url: str = "http://localhost:8000"

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
