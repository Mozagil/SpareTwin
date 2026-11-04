"""PDF durum raporu."""

import io

import pypdf
from PIL import Image

from conftest import asset_id, auth, part_id


def jpg(shade: int = 90) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (400, 300), (shade, shade, shade)).save(b, format="JPEG")
    return b.getvalue()


def pdf_text(content: bytes) -> tuple[str, int, int]:
    r = pypdf.PdfReader(io.BytesIO(content))
    images = sum(len(p.images) for p in r.pages)
    return "\n".join(p.extract_text() for p in r.pages), len(r.pages), images


def test_filo_raporu(client, manager):
    r = client.get("/reports/fleet.pdf", headers=manager)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert 'filename="sparetwin-filo-raporu-' in r.headers["content-disposition"]
    text, pages, images = pdf_text(r.content)
    for s in ("Filo durum raporu", "Hazırlayan: Demo Yönetici", "Öncelikli işler", "Lastik maliyeti, saat başına",
              "Stok uyarıları", "LD-07", "RS-02", "Kritik", "ömrü aştı", "Sayfa 1 /"):
        assert s in text, s
    assert images == 0  # henüz tamamlanmış kontrol fotoğrafı yok


def test_tek_makine_raporu_ve_firma_kontrolu(client, manager, other):
    ld07 = asset_id(client, manager, "LD-07")
    r = client.get("/reports/fleet.pdf", headers=manager, params={"asset_id": ld07})
    assert r.status_code == 200 and 'sparetwin-LD-07-' in r.headers["content-disposition"]
    text, _, _ = pdf_text(r.content)
    assert "LD-07 makine durum raporu" in text
    assert "RS-02" not in text and "Stok uyarıları" not in text
    # Başka firma demo makinesinin raporunu alamaz; kendi (boş) filosunun raporunu alır
    assert client.get("/reports/fleet.pdf", headers=other, params={"asset_id": ld07}).status_code == 404
    text, _, _ = pdf_text(client.get("/reports/fleet.pdf", headers=other).content)
    assert "BF-01" in text and "Takip gerektiren parça yok" in text and "LD-07" not in text


def test_fotograf_yalnizca_tamamlanmis_kontrolden(client, manager, tech):
    fl14 = asset_id(client, tech, "FL-14")
    tires = [p for p in client.get(f"/assets/{fl14}", headers=tech).json()["positions"] if p["category_code"] == "tire"]

    def inspection(value: float, complete: bool):
        iid = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 9400}).json()["id"]
        client.put(f"/inspections/{iid}/measurements", headers=tech, json={"items": [
            {"part_item_id": t["part_item_id"], "metric": "tread_depth_mm", "value": value} for t in tires]})
        for i, t in enumerate(tires):  # her lastiğe farklı fotoğraf (aynı görsel PDF'e bir kez gömülür)
            for angle in ("tread", "sidewall"):
                client.post(f"/inspections/{iid}/photos", headers=tech,
                            files={"file": ("f.jpg", jpg(60 + 30 * i + (5 if angle == "sidewall" else 0)), "image/jpeg")},
                            data={"part_item_id": t["part_item_id"], "angle": angle})
        if complete:
            assert client.post(f"/inspections/{iid}/complete", headers=tech).json()["status"] == "completed"

    # Taslak kontrolün fotoğrafları rapora girmez
    inspection(7, complete=False)
    _, _, images = pdf_text(client.get("/reports/fleet.pdf", headers=manager, params={"asset_id": fl14}).content)
    assert images == 0
    # Tamamlanınca: 7 mm → (7-5)/(22-5) = %12 kritik; 4 lastiğin taban fotoğrafı
    inspection(7, complete=True)
    text, _, images = pdf_text(client.get("/reports/fleet.pdf", headers=manager, params={"asset_id": fl14}).content)
    assert images == 4
    assert "son saha fotoğrafları" in text


def test_izleyici_de_rapor_alabilir(client):
    from sparetwin.db import owner_tx

    with owner_tx() as conn:
        conn.execute("""insert into public.app_users (email, password_hash, full_name)
                        select 'izleyici2@demo.sparetwin.dev', password_hash, 'İzleyici'
                          from public.app_users where email = 'yonetici@demo.sparetwin.dev'""")
        conn.execute("""insert into public.memberships (tenant_id, user_id, role)
                        select '11111111-1111-1111-1111-111111111111', id, 'viewer'
                          from public.app_users where email = 'izleyici2@demo.sparetwin.dev'""")
    assert client.get("/reports/fleet.pdf", headers=auth(client, "izleyici2@demo.sparetwin.dev")).status_code == 200
