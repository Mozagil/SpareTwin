"""Dosya deposu soyutlaması.

- LocalStorage: Diskte saklar. Geliştirme ve müşteri sunucusu kurulumu için.
  Dosyalar API üzerinden, kısa ömürlü imzalı link ile verilir.
- S3Storage: S3 uyumlu herhangi bir depo (AWS S3, Hetzner Object Storage,
  Cloudflare R2, müşterinin kendi S3 uyumlu sunucusu). Linkler S3'ün kendi
  imzalı (presigned) adresleridir.

Erişim kontrolü her zaman API'de, attachments tablosu üzerinden yapılır;
depo hiçbir zaman herkese açık değildir.
"""

from pathlib import Path
from typing import Protocol

from .config import Settings
from .security import create_media_token

ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
}


def sniff_mime(head: bytes) -> str | None:
    """Dosyanın ilk baytlarından gerçek türünü bulur (uzantıya güvenmeyiz)."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
        return "image/heic"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


class Storage(Protocol):
    def put(self, key: str, data: bytes, mime: str) -> None: ...
    def signed_url(self, key: str, mime: str, file_name: str | None) -> str: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = Path(settings.storage_local_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("Geçersiz dosya anahtarı")
        return p

    def put(self, key: str, data: bytes, mime: str) -> None:
        p = self.path_for(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(p)

    def signed_url(self, key: str, mime: str, file_name: str | None) -> str:
        token = create_media_token(self.settings, key, mime, file_name)
        return f"{self.settings.public_base_url.rstrip('/')}/media/file/{token}"

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self, settings: Settings):
        import boto3  # yalnızca S3 kullanılıyorsa yüklenir

        self.settings = settings
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )

    def put(self, key: str, data: bytes, mime: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime)

    def signed_url(self, key: str, mime: str, file_name: str | None) -> str:
        params = {"Bucket": self.bucket, "Key": key, "ResponseContentType": mime}
        if file_name:
            params["ResponseContentDisposition"] = f'inline; filename="{file_name}"'
        return self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=self.settings.media_url_minutes * 60
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(settings)
    return LocalStorage(settings)
