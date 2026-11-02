"""Excel / CSV ile toplu lastik içe aktarma."""

import io

from openpyxl import Workbook, load_workbook

from conftest import asset_id, auth


def xlsx(header: list[str], rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Lastikler"
    ws.append(header)
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


H = ["Makine kodu", "Pozisyon", "Lastik ebadı", "Marka", "Yapı", "Orijinal diş (mm)", "Hurda sınırı (mm)", "Seri no",
     "Takıldığı motor saati", "Önceki çalışma saati", "Son diş derinliği (mm)", "Ölçüm tarihi", "Alış fiyatı",
     "Makine markası", "Makine modeli", "Makine tipi", "Makine motor saati"]

# Yeni bir makine (LD-30) ve yeni bir lastik tipi, 4 lastik
GOOD = [
    ["LD-30", "A1-L", "26.5R25", "Bridgestone", "radyal", 40, 6, "BS26-9001", 4000, 0, 33, "20.10.2026", 7600, "Caterpillar", "980M", "yükleyici", 5200],
    ["LD-30", "A1-R", "26.5R25", "Bridgestone", None, None, None, "BS26-9002", 4000, 0, "32,5", "20.10.2026", None, None, None, None, None],
    ["LD-30", "A2-L", "26.5R25", "Bridgestone", None, None, None, "BS26-9003", 4000, 0, 35, "20.10.2026", None, None, None, None, None],
    ["LD-30", "a2-r", "26.5r25", "Bridgestone", None, None, None, "BS26-9004", 4000, 0, None, None, None, None, None, None, None],
]


def post(client, h, data: bytes, name="liste.xlsx", dry_run=True):
    return client.post("/import/tires", headers=h, params={"dry_run": str(dry_run).lower()},
                       files={"file": (name, data, "application/octet-stream")})


def test_sablon_indirilir_ve_gecerli_excel(client, manager):
    r = client.get("/import/tires/template", headers=manager)
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Lastikler", "Açıklama"]
    assert wb["Lastikler"]["A1"].value == "Makine kodu *"
    # Şablonun kendisi, içindeki örnek satırlarla önizlemeden geçer
    p = post(client, manager, r.content, "sablon.xlsx").json()
    assert p["summary"]["errors"] == 0 and p["summary"]["total"] == 3


def test_onizleme_hicbir_sey_yazmaz(client, manager):
    before = len(client.get("/parts", headers=manager, params={"limit": 500}).json())
    r = post(client, manager, xlsx(H, GOOD))
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    # Yeni makine ve katalog uyarısı yalnızca ilk satırda; diğer satırlar hazır
    assert s == {"total": 4, "ok": 3, "warnings": 1, "errors": 0, "new_assets": 1, "new_catalog": 1, "with_tread": 3}
    assert len(client.get("/parts", headers=manager, params={"limit": 500}).json()) == before
    assert "LD-30" not in [a["code"] for a in client.get("/assets", headers=manager).json()]


def test_hatalar_satir_satir_ve_anlasilir(client, manager):
    bad = [
        ["LD-99", "A1-L", "29.5R25", "Michelin", None, None, None, "X-1", None, None, None, None, None, None, None, None, None],
        ["LD-07", "A3-L", "29.5R25", "Michelin", None, None, None, "X-2", None, None, None, None, None, None, None, None, None],
        ["LD-07", "A1-L", "29.5R25", "Michelin", None, None, None, "X-3", None, None, None, None, None, None, None, None, None],
        ["LD-07", "A2-L", "29.5R25", "Michelin", None, None, None, "MX29-0412", None, None, None, None, None, None, None, None, None],
        ["LD-09", "MAIN-PUMP", "29.5R25", "Michelin", None, None, None, "X-5", None, None, None, None, None, None, None, None, None],
        ["LD-30", "A1-L", "26.5R25", "Bridgestone", "radyal", 40, 6, "D-1", 100, 0, "otuz", None, None, "Caterpillar", "980M", "yükleyici", 5200],
        ["LD-30", "A1-L", "26.5R25", "Bridgestone", None, None, None, "D-1", 99999, 0, 50, "31.31.2026", None, None, None, None, None],
        ["FL-14", "A1-L", "40.00R57", "Yok", None, None, None, "Z-1", None, None, None, None, None, None, None, None, None],
    ]
    r = post(client, manager, xlsx(H, bad)).json()
    e = {row["row"]: " | ".join(row["errors"]) for row in r["rows"]}
    assert "'LD-99' diye bir makine yok" in e[2]
    assert "A3-L pozisyonu yok" in e[3] and "A1-L, A1-R, A2-L, A2-R" in e[3]
    assert "LD-07 A1-L dolu" in e[4]
    assert "MX29-0412 zaten kayıtlı" in e[5]
    assert "lastik pozisyonu değil" in e[6]
    assert "sayı değil: 'otuz'" in e[7]
    assert "dosyada iki kez var (satır 7)" in e[8]          # aynı pozisyon
    assert "Seri no D-1 dosyada iki kez var" in e[8]
    assert "Ölçüm tarihi anlaşılamadı" in e[8]
    assert "büyük olamaz" in e[8]                            # 99999 > 5200 ve 50 > 40
    assert "Yapı" in e[9] and "Orijinal diş" in e[9]         # yeni ebat için bilgi eksik
    assert r["summary"]["errors"] == 8


def test_hata_varsa_hicbir_sey_kaydedilmez(client, manager):
    rows = GOOD + [["LD-99", "A1-L", "26.5R25", "Bridgestone", None, None, None, "Q-1"] + [None] * 9]
    r = post(client, manager, xlsx(H, rows), dry_run=False)
    assert r.status_code == 422
    assert "hiçbir şey kaydedilmedi" in r.json()["detail"]
    assert "LD-30" not in [a["code"] for a in client.get("/assets", headers=manager).json()]


def test_ice_aktarma_uctan_uca(client, manager):
    r = post(client, manager, xlsx(H, GOOD), dry_run=False)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == {"assets": 1, "models": 1, "catalog": 1, "tires": 4, "measurements": 3}
    assert len(r.json()["part_ids"]) == 4

    ld30 = asset_id(client, manager, "LD-30")
    a = client.get(f"/assets/{ld30}", headers=manager).json()
    assert float(a["meter_hours"]) == 5200 and a["qr_code"].startswith("ST-A-")
    tires = {p["code"]: p for p in a["positions"] if p["category_code"] == "tire"}
    assert all(t["part_item_id"] for t in tires.values())
    # Ölçümlü lastiklerde sağlık hemen hesaplanır: (33-6)/(40-6) = %79,4; ölçümsüz olan "ölçüm bekliyor"
    assert float(tires["A1-L"]["condition_pct"]) == 79.4 and tires["A1-L"]["band"] == "ok"
    assert float(tires["A1-R"]["condition_pct"]) == 77.9  # "32,5" Türkçe ondalık
    assert tires["A2-R"]["band"] == "unknown"
    # Kalan ömür: 1200 saatte 7 mm aşınmış → 27 mm / (7/1200) ≈ 4629 saat
    assert tires["A1-L"]["projected_hours_left"] == 4629
    ev = [e["event_type"] for e in client.get(f"/parts/{tires['A1-L']['part_item_id']}/events", headers=manager).json()]
    assert ev == ["installed", "received"]

    # Aynı dosya tekrar yüklenirse: seri no'lar ve pozisyonlar artık dolu
    again = post(client, manager, xlsx(H, GOOD)).json()
    assert again["summary"]["errors"] == 4
    assert any("zaten kayıtlı" in m for m in again["rows"][0]["errors"])


def test_csv_noktali_virgul_turkce_karakter(client, manager):
    csv = ("Makine;Pozisyon;Ebat;Marka;Seri numarası;Son diş derinliği;Takıldığı motor saati\n"
           "FL-14;A1-L;7.00-12;Trelleborg;TB7-CSV1;14,5;9000\n").encode("cp1254")
    # FL-14 A1-L dolu olduğu için hata beklenir; amaç: dosya ve başlıklar doğru okunuyor mu
    r = post(client, manager, csv, "liste.csv").json()
    row = r["rows"][0]
    assert row["asset_code"] == "FL-14" and row["serial_no"] == "TB7-CSV1" and float(row["tread_mm"]) == 14.5
    assert any("dolu" in m for m in row["errors"])


def test_dosya_hatalari(client, manager):
    assert "xls" in post(client, manager, b"\xd0\xcf\x11\xe0eski", "eski.xls").json()["detail"]
    assert "Başlık satırı bulunamadı" in post(client, manager, xlsx(["a", "b"], [[1, 2]])).json()["detail"]
    assert "Zorunlu sütun eksik: Lastik ebadı" in post(client, manager, xlsx(["Makine kodu", "Pozisyon"], [["LD-07", "A1-L"]])).json()["detail"]
    assert "açılamadı" in post(client, manager, b"PK\x03\x04bozuk", "bozuk.xlsx").json()["detail"]


def test_teknisyen_ice_aktaramaz(client, tech):
    assert client.get("/import/tires/template", headers=tech).status_code == 403
    assert post(client, tech, xlsx(H, GOOD)).status_code == 403
