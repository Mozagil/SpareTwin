import boto3
from moto import mock_aws

from conftest import asset_id
from sparetwin.config import Settings
from sparetwin.storage import S3Storage, sniff_mime

import io

from PIL import Image


def _img(fmt: str) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 120, 120)).save(b, format=fmt)
    return b.getvalue()


JPEG = _img("JPEG")  # gerçek, açılabilir görseller (yüklemede işlendikleri için)
PNG = _img("PNG")


def _fl14_tires(client, h):
    a = client.get(f"/assets/{asset_id(client, h, 'FL-14')}", headers=h).json()
    return a["id"], [p for p in a["positions"] if p["category_code"] == "tire"]


def test_inspeksiyon_kalite_kapilari_uctan_uca(client, tech):
    fl14, tires = _fl14_tires(client, tech)
    assert len(tires) == 4

    ins = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 9400})
    assert ins.status_code == 201, ins.text
    iid = ins.json()["id"]

    # 1) Hiçbir şey girilmeden tamamlama: taslak kalır, eksikler listelenir
    r = client.post(f"/inspections/{iid}/complete", headers=tech).json()
    assert r["status"] == "draft"
    gates = {f["gate"] for f in r["qc_flags"]}
    assert gates == {"KK2", "KK3"}

    # 2) Aralık dışı ölçüm: KK3 yine yakalar
    client.put(f"/inspections/{iid}/measurements", headers=tech, json={"items": [
        {"part_item_id": t["part_item_id"], "metric": "tread_depth_mm", "value": 999, "unit": "mm"} for t in tires
    ]})
    r = client.post(f"/inspections/{iid}/complete", headers=tech).json()
    assert any("aralık dışında" in f["message"] for f in r["qc_flags"])

    # 3) Düzeltilmiş ölçümler (aynı parça+ölçüm tekrar gönderilince güncellenir)
    r = client.put(f"/inspections/{iid}/measurements", headers=tech, json={"items": [
        {"part_item_id": t["part_item_id"], "metric": "tread_depth_mm", "value": 12, "unit": "mm"} for t in tires
    ]})
    assert r.json() == {"saved": 4}
    detail = client.get(f"/inspections/{iid}", headers=tech).json()
    assert len(detail["measurements"]) == 4

    # 4) Zorunlu fotoğraflar
    for t in tires:
        for angle in ("tread", "sidewall"):
            up = client.post(
                f"/inspections/{iid}/photos", headers=tech,
                files={"file": ("foto.jpg", JPEG, "image/jpeg")},
                data={"part_item_id": t["part_item_id"], "angle": angle},
            )
            assert up.status_code == 201, up.text

    # Aynı açı tekrar yüklenince eskisinin yerine geçer
    client.post(
        f"/inspections/{iid}/photos", headers=tech,
        files={"file": ("yeni.png", PNG, "image/png")},
        data={"part_item_id": tires[0]["part_item_id"], "angle": "tread"},
    )
    assert len(client.get(f"/inspections/{iid}", headers=tech).json()["photos"]) == 8

    # 5) Tamam
    r = client.post(f"/inspections/{iid}/complete", headers=tech).json()
    assert r["status"] == "completed", r["qc_flags"]
    assert r["qc_flags"] == []

    # Motor saati inspeksiyondan güncellendi
    assert float(client.get(f"/assets/{fl14}", headers=tech).json()["meter_hours"]) == 9400

    # 6) Tamamlanan inspeksiyon değiştirilemez
    r = client.put(f"/inspections/{iid}/measurements", headers=tech, json={"items": [
        {"part_item_id": tires[0]["part_item_id"], "metric": "tread_depth_mm", "value": 11}
    ]})
    assert r.status_code == 409


def test_desteklenmeyen_dosya_ve_boyut(client, tech, settings):
    fl14, tires = _fl14_tires(client, tech)
    iid = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 9450}).json()["id"]
    pid = tires[0]["part_item_id"]

    # Uzantısı .jpg ama içeriği çalıştırılabilir dosya
    r = client.post(f"/inspections/{iid}/photos", headers=tech,
                    files={"file": ("foto.jpg", b"MZ\x90\x00" + b"\x00" * 50, "image/jpeg")},
                    data={"part_item_id": pid, "angle": "tread"})
    assert r.status_code == 415

    big = JPEG + b"\x00" * settings.media_max_bytes
    r = client.post(f"/inspections/{iid}/photos", headers=tech,
                    files={"file": ("buyuk.jpg", big, "image/jpeg")},
                    data={"part_item_id": pid, "angle": "tread"})
    assert r.status_code == 413


def test_fotograf_linki_ve_baska_firma_erisimi(client, tech, other):
    fl14, tires = _fl14_tires(client, tech)
    iid = client.post("/inspections", headers=tech, json={"asset_id": fl14, "asset_hours": 9460}).json()["id"]
    photo = client.post(f"/inspections/{iid}/photos", headers=tech,
                        files={"file": ("f.jpg", JPEG, "image/jpeg")},
                        data={"part_item_id": tires[0]["part_item_id"], "angle": "tread"}).json()

    link = client.get(f"/media/{photo['id']}/url", headers=tech).json()
    assert link["expires_in"] == 600
    path = link["url"].replace("http://testserver", "")
    f = client.get(path)  # oturum başlığı olmadan, <img src> gibi
    assert f.status_code == 200
    assert f.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(f.content)).size == (64, 48)  # işlenmiş ama aynı görsel

    assert client.get("/media/file/sahte-token").status_code == 403
    assert client.get(f"/media/{photo['id']}/url", headers=other).status_code == 404


def test_baska_firma_makinesine_inspeksiyon_acilamaz(client, other, tech):
    fl14, _ = _fl14_tires(client, tech)
    assert client.post("/inspections", headers=other, json={"asset_id": fl14}).status_code == 404


def test_mime_tespiti():
    assert sniff_mime(JPEG[:16]) == "image/jpeg"
    assert sniff_mime(PNG[:16]) == "image/png"
    assert sniff_mime(b"%PDF-1.7\n") == "application/pdf"
    assert sniff_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_mime(b"<html>") is None


@mock_aws
def test_s3_deposu(tmp_path):
    s = Settings(env="test", jwt_secret="x" * 40, storage_backend="s3", s3_bucket="test-bucket",
                 s3_access_key="test", s3_secret_key="test", s3_region="eu-central-1")
    boto3.client("s3", region_name="eu-central-1").create_bucket(
        Bucket="test-bucket", CreateBucketConfiguration={"LocationConstraint": "eu-central-1"})
    st = S3Storage(s)
    st.put("t1/inspection/x/a.jpg", JPEG, "image/jpeg")
    url = st.signed_url("t1/inspection/x/a.jpg", "image/jpeg", "a.jpg")
    assert "test-bucket" in url and "Signature" in url or "X-Amz-Signature" in url
    obj = boto3.client("s3", region_name="eu-central-1").get_object(Bucket="test-bucket", Key="t1/inspection/x/a.jpg")
    assert obj["Body"].read() == JPEG
    st.delete("t1/inspection/x/a.jpg")
