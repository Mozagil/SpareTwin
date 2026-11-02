"""Yüklenen görsellerin işlenmesi.

- Telefonun kaydettiği yöne göre döndürülür (EXIF Orientation).
- Uzun kenarı en fazla 1600 px olacak şekilde küçültülür (sahada mobil veri).
- Tüm meta veri silinir: konum (GPS), cihaz bilgisi vb. dosyada kalmaz.
- Saydamlık yoksa JPEG, varsa PNG olarak yeniden kaydedilir.
HEIC (iPhone) ve PDF işlenmeden olduğu gibi saklanır.
"""

import io

from PIL import Image, ImageOps

MAX_SIDE = 1600
Image.MAX_IMAGE_PIXELS = 60_000_000  # sıkıştırma bombasına karşı üst sınır

PROCESSABLE = {"image/jpeg", "image/png", "image/webp"}


class ImageError(ValueError):
    pass


def process_image(data: bytes, mime: str) -> tuple[bytes, str]:
    """(yeni içerik, yeni mime). İşlenemeyen türler aynen döner."""
    if mime not in PROCESSABLE:
        return data, mime
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            im = ImageOps.exif_transpose(im)
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
            out = io.BytesIO()
            if has_alpha:
                im.save(out, format="PNG", optimize=True)  # meta veri yazılmaz
                return out.getvalue(), "image/png"
            im.convert("RGB").save(out, format="JPEG", quality=85, optimize=True, progressive=True)
            return out.getvalue(), "image/jpeg"
    except (OSError, Image.DecompressionBombError, ValueError) as e:
        raise ImageError("Görsel okunamadı veya çok büyük") from e
