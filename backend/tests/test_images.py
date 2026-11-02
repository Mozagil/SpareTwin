"""Görseller: katalog / model / makine görseli, saha fotoğrafları, gizlilik (GPS silme)."""

import io

import pytest
from PIL import Image

from conftest import asset_id, part_id


def phone_photo(w=3000, h=2000, orientation=6, gps=True) -> bytes:
    """Telefonla yan tutularak çekilmiş, içinde konum bilgisi olan bir fotoğraf."""
    im = Image.new("RGB", (w, h), (90, 110, 130))
    exif = im.getexif()
    exif[0x0112] = orientation  # 6 = 90° döndürülmesi gerekiyor
    exif[0x010F] = "TelefonMarkasi"  # Make
    if gps:
        gps_ifd = exif.get_ifd(0x8825)
        gps_ifd[1] = "N"
        gps_ifd[2] = (41.0, 0.0, 0.0)
        gps_ifd[3] = "E"
        gps_ifd[4] = (29.0, 0.0, 0.0)
    out = io.BytesIO()
    im.save(out, format="JPEG", exif=exif, quality=80)
    return out.getvalue()


def fetch(client, url: str) -> Image.Image:
    r = client.get(url.replace("http://testserver", ""))
    assert r.status_code == 200, r.text
    return Image.open(io.BytesIO(r.content))


def catalog_part_id(client, h, serial: str) -> str:
    return client.get(f"/parts/{part_id(client, h, serial)}", headers=h).json()["part_id"]


def test_test_fotografi_gercekten_gps_ve_yon_iceriyor():
    im = Image.open(io.BytesIO(phone_photo()))
    assert im.getexif()[0x0112] == 6
    assert im.getexif().get_ifd(0x8825)[1] == "N"


def test_katalog_gorseli_islenir_ve_gizli_bilgiler_silinir(client, manager):
    item = part_id(client, manager, "MX29-0412")
    cat = catalog_part_id(client, manager, "MX29-0412")
    r = client.put(f"/catalog/parts/{cat}/image", headers=manager,
                   files={"file": ("lastik.jpg", phone_photo(), "image/jpeg")})
    assert r.status_code == 200, r.text

    p = client.get(f"/parts/{item}", headers=manager).json()
    im = fetch(client, p["image"]["url"])
    assert im.format == "JPEG"
    assert im.size == (1067, 1600)  # 90° döndürüldü (dikey oldu) ve 1600 px'e küçültüldü
    assert len(im.getexif()) == 0  # GPS, cihaz markası, yön: hiçbiri kalmadı

    # Aynı katalog kalemindeki başka lastikte de aynı görsel görünür
    other = client.get(f"/parts/{part_id(client, manager, 'MX29-0413')}", headers=manager).json()
    assert other["image"]["id"] == p["image"]["id"]

    # Katalog listesinde de görünür
    row = next(c for c in client.get("/catalog/parts", headers=manager).json() if c["id"] == cat)
    assert row["image"]["url"]


def test_yeni_gorsel_eskisinin_yerine_gecer_ve_eski_dosya_silinir(client, manager, settings):
    cat = catalog_part_id(client, manager, "MX29-0412")
    before = {p for p in settings.storage_local_dir.rglob("*") if p.is_file()}
    png = io.BytesIO()
    Image.new("RGBA", (400, 300), (0, 120, 140, 128)).save(png, format="PNG")
    r = client.put(f"/catalog/parts/{cat}/image", headers=manager, files={"file": ("seffaf.png", png.getvalue(), "image/png")})
    assert r.status_code == 200
    after = {p for p in settings.storage_local_dir.rglob("*") if p.is_file()}
    assert len(after) == len(before)  # biri eklendi, eskisi silindi
    assert fetch(client, r.json()["url"]).format == "PNG"  # saydamlık korunur


def test_gorsel_silme(client, manager):
    item = part_id(client, manager, "MX29-0412")
    cat = catalog_part_id(client, manager, "MX29-0412")
    assert client.delete(f"/catalog/parts/{cat}/image", headers=manager).status_code == 204
    assert client.get(f"/parts/{item}", headers=manager).json()["image"] is None
    assert client.delete(f"/catalog/parts/{cat}/image", headers=manager).status_code == 404


def test_yetki_tur_ve_firma_kontrolleri(client, manager, tech, other):
    cat = catalog_part_id(client, manager, "MX29-0412")
    jpg = phone_photo(400, 300, gps=False)
    assert client.put(f"/catalog/parts/{cat}/image", headers=tech, files={"file": ("a.jpg", jpg, "image/jpeg")}).status_code == 403
    assert client.put(f"/catalog/parts/{cat}/image", headers=other, files={"file": ("a.jpg", jpg, "image/jpeg")}).status_code == 404
    pdf = b"%PDF-1.7\n" + b"0" * 100
    assert client.put(f"/catalog/parts/{cat}/image", headers=manager, files={"file": ("a.pdf", pdf, "application/pdf")}).status_code == 415
    bozuk = b"\xff\xd8\xff\xe0" + b"bozuk" * 20  # JPEG gibi başlıyor ama değil
    assert client.put(f"/catalog/parts/{cat}/image", headers=manager, files={"file": ("a.jpg", bozuk, "image/jpeg")}).status_code == 422


def test_makine_gorseli_modelden_gelir_kendi_fotografi_onune_gecer(client, manager):
    ld09 = asset_id(client, manager, "LD-09")
    a = client.get(f"/assets/{ld09}", headers=manager).json()
    assert a["image"] is None

    r = client.put(f"/catalog/asset-models/{a['model_id']}/image", headers=manager,
                   files={"file": ("l220h.jpg", phone_photo(1200, 800, orientation=1, gps=False), "image/jpeg")})
    assert r.status_code == 200, r.text
    a = client.get(f"/assets/{ld09}", headers=manager).json()
    assert a["image"]["source"] == "model"
    # Aynı modeldeki LD-07 de görür
    assert client.get(f"/assets/{asset_id(client, manager, 'LD-07')}", headers=manager).json()["image"]["source"] == "model"

    r = client.put(f"/assets/{ld09}/image", headers=manager,
                   files={"file": ("ld09.jpg", phone_photo(800, 600, orientation=1, gps=False), "image/jpeg")})
    assert r.status_code == 200
    assert client.get(f"/assets/{ld09}", headers=manager).json()["image"]["source"] == "asset"

    fleet = {x["code"]: x for x in client.get("/assets", headers=manager).json()}
    assert fleet["LD-09"]["image"]["url"] and fleet["LD-07"]["image"]["url"]
    assert fleet["RS-02"]["image"] is None


def test_saha_fotograflari_parca_ikizinde_ve_gps_silinmis(client, tech):
    fl14 = asset_id(client, tech, "FL-14")
    tire = part_id(client, tech, "TB7-3301")
    iid = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 9400}).json()["id"]
    r = client.post(f"/inspections/{iid}/photos", headers=tech,
                    files={"file": ("taban.jpg", phone_photo(), "image/jpeg")},
                    data={"part_item_id": tire, "angle": "tread"})
    assert r.status_code == 201, r.text

    photos = client.get(f"/parts/{tire}", headers=tech).json()["photos"]
    assert len(photos) == 1 and photos[0]["angle"] == "tread"
    im = fetch(client, photos[0]["url"])
    assert len(im.getexif()) == 0
    assert max(im.size) == 1600


@pytest.mark.parametrize("size", [(4000, 3000), (800, 600)])
def test_kucuk_gorsel_buyutulmez_buyuk_kucultulur(size):
    from sparetwin.images import process_image

    buf = io.BytesIO()
    Image.new("RGB", size).save(buf, format="JPEG")
    data, mime = process_image(buf.getvalue(), "image/jpeg")
    out = Image.open(io.BytesIO(data))
    assert mime == "image/jpeg"
    assert max(out.size) == min(max(size), 1600)
