"""Mühendislik ağacı (eBOM) ve eBOM → mBOM kuralları (0025)."""

import io
from decimal import Decimal as D
from uuid import uuid4

import pytest
from openpyxl import Workbook

from sparetwin.ebom import convert

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------- Dönüşüm (saf hesap) ----------
def rule(action, **kw):
    return {"action": action, "is_active": True, "match_part_id": None, "match_category": None, "target_part_id": None,
            "qty": None, "per": None, "scrap_pct": None, "label": kw.pop("label", action), **kw}


P, SHEET, BOLT, DOC, ARM, PIN, SEAL, OIL, BOLT2 = (uuid4() for _ in range(9))
PARTS = {SHEET: {"category_code": "sheet"}, BOLT: {"category_code": "fastener"}, DOC: {"category_code": "drawing"},
         ARM: {"category_code": "assembly"}, PIN: {"category_code": "fastener"}, SEAL: {"category_code": "seal"},
         OIL: {"category_code": "oil"}, BOLT2: {"category_code": "fastener"}}
EDGES = {P: [{"part_id": SHEET, "qty": D(2)}, {"part_id": BOLT, "qty": D(8)}, {"part_id": DOC, "qty": D(1)},
             {"part_id": ARM, "qty": D(2)}],
         ARM: [{"part_id": PIN, "qty": D(3)}, {"part_id": BOLT, "qty": D(1)}]}


def qty(out):
    return {l["part_id"]: l["qty"] for l in out["lines"]}


def test_kuralsiz_donusum_ebomun_aynisidir():
    out = convert(P, EDGES, [], PARTS)
    assert qty(out) == {SHEET: D(2), BOLT: D(8), DOC: D(1), ARM: D(2)} and out["removed"] == []
    assert all(l["ebom_qty"] == l["qty"] and l["rules"] == [] for l in out["lines"])


def test_duzlestir_alt_montaji_acar_ve_ayni_kalemi_toplar():
    out = convert(P, EDGES, [rule("flatten", match_category="assembly")], PARTS)
    assert qty(out) == {SHEET: D(2), BOLT: D(10), DOC: D(1), PIN: D(6)}
    assert [(r["part_id"], r["action"], r["qty"]) for r in out["removed"]] == [(ARM, "flatten", D(2))]


def test_cikar_degistir_ekle_fire_sirasiyla_uygulanir():
    rules = [
        rule("scrap", scrap_pct=D(5), label="fire-hepsi"),                       # en genel
        rule("scrap", match_category="fastener", scrap_pct=D(10), label="fire-civata"),
        rule("add", target_part_id=SEAL, qty=D(1), per="match", match_part_id=ARM, label="kece"),
        rule("add", target_part_id=OIL, qty=D("0.5"), per="product", label="yag"),
        rule("substitute", match_part_id=BOLT, target_part_id=BOLT2, qty=D(1), label="civata"),
        rule("exclude", match_category="drawing", label="dokuman"),
        rule("add", target_part_id=OIL, qty=D(9), per="product", is_active=False),   # kapalı kural sayılmaz
    ]
    out = convert(P, EDGES, rules, PARTS)
    # BOLT → BOLT2 ve cıvata firesi %10 (özel kural geneli ezer); diğerleri %5
    assert qty(out) == {SHEET: D("2.1"), BOLT2: D("8.8"), ARM: D("2.1"), SEAL: D("2.1"), OIL: D("0.525")}
    by = {l["part_id"]: l for l in out["lines"]}
    assert by[BOLT2]["from_part_id"] == BOLT and by[BOLT2]["rules"] == ["civata", "fire-civata"]
    assert by[SEAL]["ebom_qty"] is None and by[SEAL]["rules"] == ["kece", "fire-hepsi"]
    assert [(r["part_id"], r["action"]) for r in out["removed"]] == [(DOC, "exclude")]


def test_urun_basina_ekleme_yalnizca_eslesen_urunde_yapilir():
    only_with_pin = [rule("add", target_part_id=OIL, qty=D(1), per="product", match_part_id=PIN)]
    assert OIL not in qty(convert(P, EDGES, only_with_pin, PARTS))       # PIN alt montajın içinde, düzleştirilmedi
    assert qty(convert(ARM, EDGES, only_with_pin, PARTS))[OIL] == D(1)


# ---------- API ----------
def _ok(r, code=201):
    assert r.status_code == code, r.text
    return r.json()


@pytest.fixture(scope="module")
def cat(client, manager):
    """Ürün, sac, cıvata, çizim, alt montaj, pim, boya."""
    for code, name in (("sheet", "Sac"), ("fastener", "Bağlantı elemanı"), ("drawing", "Teknik çizim"), ("assembly", "Montaj")):
        _ok(client.post("/catalog/categories", headers=manager, json={"code": code, "name": name, "is_serialized": False}))

    def mk(c, name, no, unit="adet"):
        return _ok(client.post("/catalog/parts", headers=manager, json={
            "category_code": c, "name": name, "part_no": no, "unit": unit}))["id"]

    return {"p": mk("assembly", "Kova 2,5 m³", "EB-KOVA"), "sheet": mk("sheet", "Hardox 10 mm", "EB-SAC", "kg"),
            "bolt": mk("fastener", "M20 cıvata", "EB-M20"), "doc": mk("drawing", "Kova montaj resmi", "EB-RES"),
            "arm": mk("assembly", "Kova kulağı", "EB-KULAK"), "pin": mk("fastener", "Pim 60", "EB-PIM"),
            "paint": mk("sheet", "Astar boya", "EB-BOYA", "litre")}


def _xlsx(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Ürün parça no", "Bileşen parça no", "Miktar", "Not"])
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.fixture(scope="module")
def ebom(client, manager, cat):
    r = _ok(client.post("/production/eboms/import", headers=manager, files={"file": ("ebom.xlsx", _xlsx([
        ["EB-KOVA", "EB-SAC", 120, None], ["EB-KOVA", "EB-M20", 8, None], ["EB-KOVA", "EB-RES", 1, "referans"],
        ["EB-KOVA", "EB-KULAK", 2, None], ["EB-KULAK", "EB-PIM", 1, None], ["EB-KULAK", "EB-SAC", 6, None],
    ]), XLSX)}), 200)
    assert (r["boms_created"], r["added"], r["errors"]) == (2, 6, [])
    return next(e for e in client.get("/production/eboms", headers=manager).json() if e["part_id"] == cat["p"])


def test_ebom_ice_aktarilir_urun_agacina_dokunmaz(client, manager, cat, ebom):
    assert ebom["line_count"] == 4 and ebom["mbom_id"] is None and ebom["in_sync"] is False
    assert not any(b["part_id"] == cat["p"] for b in client.get("/production/boms", headers=manager).json())
    d = _ok(client.get(f"/production/eboms/{ebom['id']}", headers=manager), 200)
    assert {l["part_no"] for l in d["lines"]} == {"EB-SAC", "EB-M20", "EB-RES", "EB-KULAK"}
    assert next(l for l in d["lines"] if l["part_no"] == "EB-KULAK")["has_ebom"] is True
    # Kural yokken önizleme eBOM'un aynısı, hepsi "yeni"
    assert len(d["mbom"]["lines"]) == 4 and all(l["status"] == "new" for l in d["mbom"]["lines"])


def test_kural_dogrulamasi_ve_yetki(client, manager, tech, cat):
    def post(body, h=manager):
        return client.post("/production/bom-rules", headers=h, json=body)

    assert post({"action": "scrap", "scrap_pct": 5}, tech).status_code == 403
    assert post({"action": "scrap"}).status_code == 422
    assert post({"action": "exclude"}).status_code == 422
    assert post({"action": "substitute", "match_part_id": cat["bolt"], "target_part_id": cat["bolt"]}).status_code == 422
    assert post({"action": "add", "target_part_id": cat["paint"], "qty": 1, "per": "match"}).status_code == 422
    assert post({"action": "exclude", "match_category": "yok-boyle"}).status_code == 404


def test_kurallar_onizlemeyi_degistirir_ve_urun_agacina_yazilir(client, manager, tech, cat, ebom):
    def post(body):
        return _ok(client.post("/production/bom-rules", headers=manager, json=body))

    flat = post({"action": "flatten", "match_part_id": cat["arm"]})
    post({"action": "exclude", "match_category": "drawing"})
    scrap = post({"action": "scrap", "match_category": "sheet", "scrap_pct": 5})
    add = post({"action": "add", "target_part_id": cat["paint"], "qty": 0.5, "per": "product"})
    assert scrap["label"] == "Fire payı %5 · Sac" and flat["label"] == "Düzleştir · Kova kulağı"
    assert add["label"] == "Sarf ekle · Astar boya 0,5 litre ürün başına"

    d = _ok(client.get(f"/production/eboms/{ebom['id']}", headers=manager), 200)
    got = {l["part_no"]: float(l["qty"]) for l in d["mbom"]["lines"]}
    # sac 120 + 2×6 = 132, +%5 = 138,6; boya sac tipinde olduğu için o da +%5
    assert got == {"EB-SAC": 138.6, "EB-M20": 8, "EB-PIM": 2, "EB-BOYA": 0.525}
    assert {(r["part_no"], r["action"]) for r in d["mbom"]["removed"]} == {("EB-KULAK", "flatten"), ("EB-RES", "exclude")}
    paint = next(l for l in d["mbom"]["lines"] if l["part_no"] == "EB-BOYA")
    assert paint["ebom_qty"] is None and paint["rules"] == [add["label"], scrap["label"]]

    assert client.post(f"/production/eboms/{ebom['id']}/apply", headers=tech).status_code == 403
    done = _ok(client.post(f"/production/eboms/{ebom['id']}/apply", headers=manager), 200)
    assert done["mbom"]["in_sync"] is True and all(l["status"] == "same" for l in done["mbom"]["lines"])
    bom = _ok(client.get(f"/production/boms/{done['mbom']['mbom_id']}", headers=manager), 200)
    assert {l["part_no"]: float(l["qty"]) for l in bom["lines"]} == got

    # Kural kapatılınca önizleme farkı gösterir; yeniden yazınca ürün ağacı güncellenir, fazlalık silinir
    _ok(client.patch(f"/production/bom-rules/{add['id']}", headers=manager, json={"is_active": False}), 200)
    _ok(client.patch(f"/production/bom-rules/{scrap['id']}", headers=manager, json={"is_active": False}), 200)
    d = _ok(client.get(f"/production/eboms/{ebom['id']}", headers=manager), 200)
    assert d["mbom"]["in_sync"] is False and [x["part_no"] for x in d["mbom"]["dropped"]] == ["EB-BOYA"]
    sac = next(l for l in d["mbom"]["lines"] if l["part_no"] == "EB-SAC")
    assert (sac["status"], float(sac["current_qty"]), float(sac["qty"])) == ("changed", 138.6, 132)
    done = _ok(client.post(f"/production/eboms/{ebom['id']}/apply", headers=manager), 200)
    bom = _ok(client.get(f"/production/boms/{done['mbom']['mbom_id']}", headers=manager), 200)
    assert {l["part_no"]: float(l["qty"]) for l in bom["lines"]} == {"EB-SAC": 132, "EB-M20": 8, "EB-PIM": 2}
    assert any(e["id"] == ebom["id"] and e["in_sync"] for e in client.get("/production/eboms", headers=manager).json())


def test_elle_satir_ekleme_silme_ve_dongu(client, manager, cat, ebom):
    arm = next(e for e in client.get("/production/eboms", headers=manager).json() if e["part_id"] == cat["arm"])
    r = client.post(f"/production/eboms/{arm['id']}/lines", headers=manager, json={"part_id": cat["p"], "qty": 1})
    assert r.status_code == 422 and "döngü" in r.json()["detail"]
    d = _ok(client.post(f"/production/eboms/{arm['id']}/lines", headers=manager, json={"part_id": cat["bolt"], "qty": 4}))
    line = next(l for l in d["lines"] if l["part_no"] == "EB-M20")
    again = client.post(f"/production/eboms/{arm['id']}/lines", headers=manager, json={"part_id": cat["bolt"], "qty": 1})
    assert again.status_code == 409
    assert client.delete(f"/production/eboms/{arm['id']}/lines/{line['line_id']}", headers=manager).status_code == 204


def test_baska_firma_ebom_ve_kurallari_gormez(client, other, ebom):
    assert client.get("/production/eboms", headers=other).json() == []
    assert client.get("/production/bom-rules", headers=other).json() == []
    assert client.get(f"/production/eboms/{ebom['id']}", headers=other).status_code == 404
    assert client.post(f"/production/eboms/{ebom['id']}/apply", headers=other).status_code == 404
