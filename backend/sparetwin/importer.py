"""Excel / CSV ile toplu lastik içe aktarma.

Akış: dosya okunur → her satır doğrulanır (hiçbir şey yazılmadan önizleme) →
onaylanınca aynı doğrulama tek işlem içinde tekrar yapılır ve ya hepsi ya hiçbiri
kaydedilir. Kurallar (pozisyon, kategori, sayaç) veritabanı fonksiyonlarından geçer.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import psycopg
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

MAX_ROWS = 2000
MAX_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Col:
    key: str
    header: str
    required: bool
    help: str
    example: str
    aliases: tuple[str, ...] = ()


COLUMNS: list[Col] = [
    Col("asset_code", "Makine kodu", True, "Filo / ekipman numarası. Sistemde yoksa aşağıdaki makine sütunlarıyla oluşturulur.", "LD-20",
        ("makine", "ekipman", "ekipman no", "filo no", "araç", "arac", "makine no")),
    Col("position", "Pozisyon", True, "Makinedeki lastik yuvası: A1-L, A1-R, A2-L, A2-R (reach stacker ön dingilde A1-LO, A1-LI, A1-RI, A1-RO).", "A1-L",
        ("poz", "pozisyon kodu", "konum", "yuva")),
    Col("size", "Lastik ebadı", True, "Örn. 29.5R25, 18.00-25, 7.00-12.", "29.5R25", ("ebat", "ebad", "lastik ebati", "boyut", "size")),
    Col("brand", "Marka", False, "Lastik üreticisi. Ebat + marka ile katalog kalemi eşleşir.", "Michelin", ("üretici", "uretici", "lastik markası")),
    Col("construction", "Yapı", False, "radyal, diyagonal veya dolgu. Katalogda olmayan yeni bir ebat/marka için zorunlu.", "radyal", ("tip", "yapi", "lastik tipi")),
    Col("otd_mm", "Orijinal diş (mm)", False, "Yeni lastiğin diş derinliği. Katalogda olmayan yeni bir ebat/marka için zorunlu.", "55",
        ("orijinal diş derinliği", "otd", "yeni diş", "orijinal dis")),
    Col("scrap_mm", "Hurda sınırı (mm)", False, "Bu derinliğe inince söküm/kaplama. Boşsa 0.", "8", ("hurda", "söküm sınırı", "min diş")),
    Col("serial_no", "Seri no", False, "Lastiğin seri numarası. Önerilir; aynı seri no iki kez girilemez.", "MX29-1001",
        ("seri", "seri numarası", "seri numarasi", "serial", "dot", "lastik no")),
    Col("installed_at_hours", "Takıldığı motor saati", False, "Lastik takıldığında makinenin motor saati. Boşsa bugünkü saat kabul edilir (çalışma 0).", "11800",
        ("takılma saati", "takildigi saat", "montaj saati")),
    Col("prev_hours", "Önceki çalışma saati", False, "Başka makinede daha önce çalıştıysa o saat. Boşsa 0.", "0", ("önceki saat", "onceki saat")),
    Col("tread_mm", "Son diş derinliği (mm)", False, "Son ölçülen diş derinliği. Girilirse kalan ömür hemen hesaplanır.", "41",
        ("diş derinliği", "dis derinligi", "son diş", "kalan diş", "tread")),
    Col("measured_at", "Ölçüm tarihi", False, "Son ölçümün tarihi (GG.AA.YYYY). Boşsa bugün.", "15.10.2026", ("tarih", "ölçüm tarih")),
    Col("cost", "Alış fiyatı", False, "Birim fiyat ($). Boşsa katalog fiyatı.", "9800", ("fiyat", "maliyet", "tutar")),
    Col("asset_manufacturer", "Makine markası", False, "Yalnızca makine sistemde yoksa: üretici.", "Volvo", ("makine üreticisi",)),
    Col("asset_model", "Makine modeli", False, "Yalnızca makine sistemde yoksa: model.", "L220H", ()),
    Col("asset_type", "Makine tipi", False, "Yalnızca makine sistemde yoksa: yükleyici, reach stacker veya forklift.", "yükleyici", ("makine türü",)),
    Col("asset_hours", "Makine motor saati", False, "Yalnızca makine sistemde yoksa: güncel motor saati.", "12500", ("güncel saat", "makine saati")),
]
BY_KEY = {c.key: c for c in COLUMNS}

LAYOUTS = {
    "loader": ("wheel_loader", {"yükleyici", "yukleyici", "lastikli yükleyici", "lastikli yukleyici", "loader", "wheel loader", "kepçe", "kepce"}),
    "reach_stacker": ("reach_stacker", {"reach stacker", "reachstacker", "konteyner istifleyici"}),
    "forklift": ("forklift", {"forklift", "fork lift"}),
}
CONSTRUCTIONS = {
    "radial": {"radyal", "radial", "r"},
    "bias": {"diyagonal", "bias", "çapraz", "capraz", "konvansiyonel"},
    "solid": {"dolgu", "solid", "masif"},
}
CONSTRUCTION_TR = {"radial": "radyal", "bias": "diyagonal", "solid": "dolgu"}


def _norm(s: Any) -> str:
    """Başlık eşleme için: küçük harf, Türkçe karakterler sadeleşir, parantez içi atılır."""
    t = str(s or "").replace("İ", "i").replace("I", "ı").lower()
    t = re.sub(r"\(.*?\)", "", t)
    t = unicodedata.normalize("NFKD", t.replace("ı", "i"))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


_HEADER_INDEX: dict[str, str] = {}
for _c in COLUMNS:
    for name in (_c.header, _c.key, *_c.aliases):
        _HEADER_INDEX[_norm(name)] = _c.key


class ImportFileError(ValueError):
    pass


# ---------- Dosya okuma ----------
def read_rows(data: bytes, filename: str) -> tuple[list[dict[str, Any]], list[str]]:
    """(satırlar, tanınmayan başlıklar). Her satırda '_row' Excel satır numarasıdır."""
    if len(data) > MAX_BYTES:
        raise ImportFileError("Dosya en fazla 5 MB olabilir")
    name = filename.lower()
    if name.endswith(".xls"):
        raise ImportFileError("Eski .xls biçimi desteklenmiyor. Excel'de 'Farklı kaydet → .xlsx' ile kaydedin.")
    if name.endswith(".csv") or not data.startswith(b"PK"):
        table = _read_csv(data)
    else:
        table = _read_xlsx(data)

    # Başlık satırı: ilk 5 satırda en çok sütun eşleşen satır
    best, best_hits = None, 0
    for i, row in enumerate(table[:5]):
        hits = sum(1 for v in row if _norm(v) in _HEADER_INDEX)
        if hits > best_hits:
            best, best_hits = i, hits
    if best is None or best_hits < 2:
        raise ImportFileError("Başlık satırı bulunamadı. Şablondaki sütun adlarını kullanın (ör. 'Makine kodu', 'Pozisyon', 'Lastik ebadı').")
    header = table[best]
    mapping: dict[int, str] = {}
    unknown: list[str] = []
    for j, h in enumerate(header):
        key = _HEADER_INDEX.get(_norm(h))
        if key and key not in mapping.values():
            mapping[j] = key
        elif str(h or "").strip():
            unknown.append(str(h).strip())
    missing = [BY_KEY[k].header for k in ("asset_code", "position", "size") if k not in mapping.values()]
    if missing:
        raise ImportFileError(f"Zorunlu sütun eksik: {', '.join(missing)}")

    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(table[best + 1:], start=best + 2):
        if not any(str(v).strip() for v in raw if v is not None):
            continue
        row = {"_row": i}
        for j, key in mapping.items():
            v = raw[j] if j < len(raw) else None
            row[key] = v.strip() if isinstance(v, str) else v
            if row[key] == "":
                row[key] = None
        rows.append(row)
    if len(rows) > MAX_ROWS:
        raise ImportFileError(f"Tek seferde en fazla {MAX_ROWS} satır içe aktarılabilir")
    if not rows:
        raise ImportFileError("Dosyada veri satırı yok")
    return rows, unknown


def _read_xlsx(data: bytes) -> list[list[Any]]:
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:  # bozuk / şifreli dosya
        raise ImportFileError("Excel dosyası açılamadı. Dosya bozuk ya da şifreli olabilir.") from e
    ws = wb["Lastikler"] if "Lastikler" in wb.sheetnames else wb.worksheets[0]
    out = [list(r) for r in ws.iter_rows(values_only=True, max_row=MAX_ROWS + 10)]
    wb.close()
    return out


def _read_csv(data: bytes) -> list[list[Any]]:
    for enc in ("utf-8-sig", "cp1254", "latin-1"):  # cp1254: Türkçe Windows Excel
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        delim = dialect.delimiter
    except csv.Error:
        delim = ";" if sample.count(";") >= sample.count(",") else ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delim)]


# ---------- Değer çözümleme ----------
def parse_number(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        raise ValueError
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    s = str(v).strip().replace(" ", "").replace("\u00a0", "")
    if "," in s and "." in s:  # 1.234,5 → 1234.5
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError


def parse_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError


def _choice(v: Any, table: dict[str, set[str]]) -> str | None:
    n = _norm(v)
    for key, names in table.items():
        if n in {_norm(x) for x in names}:
            return key
    return None


# ---------- Doğrulama ----------
@dataclass
class Row:
    n: int
    data: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    plan: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "error" if self.errors else "warning" if self.warnings else "ok"


class Context:
    """Doğrulama için veritabanından tek seferde okunan bilgiler (RLS altında)."""

    def __init__(self, conn: psycopg.Connection, tenant_id: UUID):
        self.tenant_id = tenant_id
        self.assets = {r["code"].lower(): r for r in conn.execute(
            """select a.id, a.code, a.meter_hours, am.template_id from public.assets a
                 left join public.asset_models am on am.id = a.model_id where a.tenant_id = %s""", [tenant_id]).fetchall()}
        self.positions: dict[UUID, dict[str, str]] = {}
        for r in conn.execute("select template_id, code, category_code from public.template_positions").fetchall():
            self.positions.setdefault(r["template_id"], {})[r["code"]] = r["category_code"]
        self.library_templates = {r["layout"]: r["id"] for r in conn.execute(
            "select id, layout from public.position_templates where tenant_id is null").fetchall()}
        self.models = {(r["manufacturer"].lower(), r["model"].lower()): r for r in conn.execute(
            """select id, manufacturer, model, template_id from public.asset_models
                where tenant_id = %s or tenant_id is null""", [tenant_id]).fetchall()}
        self.catalog = {}
        for r in conn.execute(
                """select p.id, p.name, coalesce(p.manufacturer, '') as manufacturer, p.list_cost,
                          ts.size, ts.otd_mm, ts.scrap_tread_mm
                     from public.parts p join public.tire_specs ts on ts.part_id = p.id
                    where p.tenant_id = %s or p.tenant_id is null""", [tenant_id]).fetchall():
            self.catalog[(r["size"].lower(), r["manufacturer"].lower())] = r
        self.serials = {r["s"] for r in conn.execute(
            """select lower(pi.serial_no) as s from public.part_items pi
                 join public.parts p on p.id = pi.part_id join public.part_categories pc on pc.id = p.category_id
                where pi.tenant_id = %s and pc.code = 'tire' and pi.serial_no is not null""", [tenant_id]).fetchall()}
        self.occupied = {(r["current_asset_id"], r["current_position"]) for r in conn.execute(
            """select current_asset_id, current_position from public.part_items
                where tenant_id = %s and status = 'installed'""", [tenant_id]).fetchall()}


def validate(ctx: Context, raw_rows: list[dict[str, Any]]) -> list[Row]:
    rows = [Row(r["_row"], r) for r in raw_rows]
    new_assets: dict[str, dict[str, Any]] = {}       # dosyada oluşturulacak makineler
    new_catalog: dict[tuple[str, str], dict[str, Any]] = {}
    used_positions: dict[tuple[str, str], int] = {}  # (makine kodu, pozisyon) → satır
    used_serials: dict[str, int] = {}

    for row in rows:
        d, E, W = row.data, row.errors, row.warnings
        num: dict[str, Decimal | None] = {}
        for key in ("otd_mm", "scrap_mm", "installed_at_hours", "prev_hours", "tread_mm", "cost", "asset_hours"):
            try:
                num[key] = parse_number(d.get(key))
                if num[key] is not None and num[key] < 0:
                    E.append(f"{BY_KEY[key].header} negatif olamaz")
            except ValueError:
                E.append(f"{BY_KEY[key].header} sayı değil: '{d.get(key)}'")
                num[key] = None
        try:
            measured = parse_date(d.get("measured_at"))
        except ValueError:
            E.append(f"Ölçüm tarihi anlaşılamadı: '{d.get('measured_at')}' (GG.AA.YYYY yazın)")
            measured = None

        code = str(d.get("asset_code") or "").strip()
        pos = str(d.get("position") or "").strip().upper()
        size = str(d.get("size") or "").strip().upper().replace(" ", "")
        brand = str(d.get("brand") or "").strip()
        for key, val in (("asset_code", code), ("position", pos), ("size", size)):
            if not val:
                E.append(f"{BY_KEY[key].header} boş")
        if not (code and pos and size):
            continue

        # --- Makine ---
        asset = ctx.assets.get(code.lower())
        template_id = asset["template_id"] if asset else None
        meter = asset["meter_hours"] if asset else None
        if asset:
            row.plan["asset"] = {"existing": True, "id": asset["id"], "code": asset["code"]}
        elif code.lower() in new_assets:
            na = new_assets[code.lower()]
            template_id, meter = na["template_id"], na["meter"]
            row.plan["asset"] = {"existing": False, "code": na["code"], "same_as_row": na["row"]}
        else:
            mf = str(d.get("asset_manufacturer") or "").strip()
            md = str(d.get("asset_model") or "").strip()
            layout = _choice(d.get("asset_type"), {k: v[1] for k, v in LAYOUTS.items()}) if d.get("asset_type") else None
            model = ctx.models.get((mf.lower(), md.lower())) if mf and md else None
            if model:
                template_id = model["template_id"]
            elif mf and md and layout:
                template_id = ctx.library_templates.get(layout)
            if not template_id:
                if not (mf and md):
                    E.append(f"'{code}' diye bir makine yok. Oluşturmak için Makine markası, Makine modeli ve Makine tipi sütunlarını doldurun.")
                elif not layout:
                    E.append(f"'{code}' yeni makine: Makine tipi 'yükleyici', 'reach stacker' veya 'forklift' olmalı")
                continue
            meter = num["asset_hours"] or Decimal(0)
            new_assets[code.lower()] = {"code": code, "template_id": template_id, "meter": meter, "row": row.n}
            row.plan["asset"] = {"existing": False, "code": code, "manufacturer": mf, "model": md,
                                 "model_id": model["id"] if model else None, "layout": layout,
                                 "category": LAYOUTS[layout][0] if layout else None,
                                 "template_id": template_id, "meter": meter}
            W.append(f"Yeni makine oluşturulacak: {code} ({mf} {md})")

        # --- Pozisyon ---
        slots = ctx.positions.get(template_id, {})
        if pos not in slots:
            E.append(f"{code} makinesinde {pos} pozisyonu yok. Geçerli lastik pozisyonları: "
                     + ", ".join(k for k, v in slots.items() if v == "tire"))
        elif slots[pos] != "tire":
            E.append(f"{pos} bir lastik pozisyonu değil")
        elif asset and (asset["id"], pos) in ctx.occupied:
            E.append(f"{code} {pos} dolu: önce mevcut lastiği sökün")
        if (code.lower(), pos) in used_positions:
            E.append(f"{code} {pos} dosyada iki kez var (satır {used_positions[(code.lower(), pos)]})")
        used_positions.setdefault((code.lower(), pos), row.n)

        # --- Katalog kalemi ---
        key = (size.lower(), brand.lower())
        cat = ctx.catalog.get(key)
        if not cat and not brand:
            # Marka yazılmadıysa ebada göre tek kalem varsa onu kullan
            same = [v for (s, _), v in ctx.catalog.items() if s == size.lower()]
            cat = same[0] if len(same) == 1 else None
        otd, scrap = num["otd_mm"], num["scrap_mm"]
        if cat:
            row.plan["catalog"] = {"existing": True, "id": cat["id"], "name": cat["name"]}
            otd, scrap = cat["otd_mm"], cat["scrap_tread_mm"]
            list_cost = cat["list_cost"]
        elif key in new_catalog:
            nc = new_catalog[key]
            row.plan["catalog"] = {"existing": False, "name": nc["name"], "same_as_row": nc["row"]}
            otd, scrap, list_cost = nc["otd"], nc["scrap"], nc["cost"]
        else:
            construction = _choice(d.get("construction"), CONSTRUCTIONS) if d.get("construction") else None
            if not construction:
                E.append(f"{size} {brand} katalogda yok: Yapı (radyal / diyagonal / dolgu) gerekli")
            if otd is None:
                E.append(f"{size} {brand} katalogda yok: Orijinal diş (mm) gerekli")
            scrap = scrap or Decimal(0)
            if otd is not None and scrap >= otd:
                E.append("Hurda sınırı, orijinal diş derinliğinden küçük olmalı")
            if construction and otd is not None:
                name = f"{size} {CONSTRUCTION_TR[construction]}".strip()
                new_catalog[key] = {"name": name, "otd": otd, "scrap": scrap, "cost": num["cost"], "row": row.n}
                row.plan["catalog"] = {"existing": False, "name": name, "size": size, "brand": brand or None,
                                       "construction": construction, "otd": otd, "scrap": scrap}
                W.append(f"Yeni katalog kalemi oluşturulacak: {size} {brand}".strip())
            list_cost = num["cost"]

        # --- Seri no ---
        serial = str(d.get("serial_no") or "").strip() or None
        if serial:
            if serial.lower() in ctx.serials:
                E.append(f"Seri no {serial} zaten kayıtlı")
            elif serial.lower() in used_serials:
                E.append(f"Seri no {serial} dosyada iki kez var (satır {used_serials[serial.lower()]})")
            used_serials.setdefault(serial.lower(), row.n)
        else:
            W.append("Seri no yok; etiketle takip edilecek")

        # --- Saatler ve ölçüm ---
        inst = num["installed_at_hours"]
        if meter is not None:
            if inst is None:
                inst = meter
                W.append("Takıldığı motor saati yok: bugünkü saat kabul edildi (lastiğin çalışması 0)")
            elif inst > meter:
                E.append(f"Takıldığı motor saati ({inst}) makinenin güncel saatinden ({meter}) büyük olamaz")
        tread = num["tread_mm"]
        if tread is not None and otd is not None and tread > otd:
            E.append(f"Son diş derinliği ({tread}) orijinal diş derinliğinden ({otd}) büyük olamaz")
        row.plan["tire"] = {"serial_no": serial, "installed_at_hours": inst, "prev_hours": num["prev_hours"] or Decimal(0),
                            "tread_mm": tread, "measured_at": measured, "cost": num["cost"] if num["cost"] is not None else list_cost,
                            "position": pos}
    return rows


def summarize(rows: list[Row]) -> dict[str, int]:
    ok = [r for r in rows if not r.errors]
    return {
        "total": len(rows),
        "ok": sum(1 for r in rows if r.status == "ok"),
        "warnings": sum(1 for r in rows if r.status == "warning"),
        "errors": sum(1 for r in rows if r.errors),
        "new_assets": sum(1 for r in ok if r.plan.get("asset", {}).get("existing") is False and "same_as_row" not in r.plan["asset"]),
        "new_catalog": sum(1 for r in ok if r.plan.get("catalog", {}).get("existing") is False and "same_as_row" not in r.plan["catalog"]),
        "with_tread": sum(1 for r in ok if r.plan.get("tire", {}).get("tread_mm") is not None),
    }


# ---------- Kaydetme ----------
def commit(conn: psycopg.Connection, tenant_id: UUID, user_id: UUID, rows: list[Row]) -> dict[str, Any]:
    """Hatasız satırları yazar. Çağıran, hata varsa çağırmamalıdır (ya hepsi ya hiçbiri)."""
    from psycopg.types.json import Jsonb

    asset_ids: dict[str, UUID] = {}
    catalog_ids: dict[str, UUID] = {}
    created = {"assets": 0, "models": 0, "catalog": 0, "tires": 0, "measurements": 0}
    part_ids: list[str] = []
    tire_cat = conn.execute("select id from public.part_categories where tenant_id is null and code = 'tire'").fetchone()["id"]

    for row in rows:
        a, c, t = row.plan["asset"], row.plan["catalog"], row.plan["tire"]
        # Makine
        if a["existing"]:
            aid = a["id"]
        elif a["code"].lower() in asset_ids:
            aid = asset_ids[a["code"].lower()]
        else:
            model_id = a.get("model_id")
            if not model_id:
                model_id = conn.execute(
                    """insert into public.asset_models (tenant_id, manufacturer, model, category, template_id)
                       values (%s, %s, %s, %s, %s) returning id""",
                    [tenant_id, a["manufacturer"], a["model"], a["category"], a["template_id"]]).fetchone()["id"]
                created["models"] += 1
            aid = conn.execute(
                """insert into public.assets (tenant_id, model_id, code, meter_hours, qr_code)
                   values (%s, %s, %s, %s, app.new_qr('ST-A-')) returning id""",
                [tenant_id, model_id, a["code"], a["meter"]]).fetchone()["id"]
            asset_ids[a["code"].lower()] = aid
            created["assets"] += 1
        # Katalog
        if c["existing"]:
            pid = c["id"]
        else:
            ck = c["name"].lower() + "|" + (c.get("brand") or row.data.get("brand") or "").lower()
            if ck in catalog_ids:
                pid = catalog_ids[ck]
            else:
                pid = conn.execute(
                    """insert into public.parts (tenant_id, category_id, manufacturer, name, specs, list_cost)
                       values (%s, %s, %s, %s, %s, %s) returning id""",
                    [tenant_id, tire_cat, c.get("brand"), c["name"] + (f" ({c['brand']})" if c.get("brand") else ""),
                     Jsonb({}), t["cost"]]).fetchone()["id"]
                conn.execute(
                    """insert into public.tire_specs (part_id, size, construction, otd_mm, scrap_tread_mm)
                       values (%s, %s, %s, %s, %s)""", [pid, c["size"], c["construction"], c["otd"], c["scrap"]])
                catalog_ids[ck] = pid
                created["catalog"] += 1
        # Lastik: stoğa al → tak (kural kontrolleri install_part_item'da)
        item = conn.execute(
            """insert into public.part_items
                 (tenant_id, part_id, serial_no, qr_code, status, hours_accumulated, purchase_cost, acquired_at)
               values (%s, %s, %s, app.new_qr('ST-P-'), 'in_stock', %s, %s, current_date) returning id""",
            [tenant_id, pid, t["serial_no"], t["prev_hours"], t["cost"]]).fetchone()["id"]
        conn.execute(
            """insert into public.part_events (tenant_id, part_item_id, event_type, part_hours, notes, performed_by)
               values (%s, %s, 'received', %s, 'Excel içe aktarma', %s)""", [tenant_id, item, t["prev_hours"], user_id])
        conn.execute("select 1 from public.install_part_item(%s, %s, %s, %s, %s)",
                     [item, aid, t["position"], t["installed_at_hours"], "Excel içe aktarma"])
        created["tires"] += 1
        part_ids.append(str(item))
        if t["tread_mm"] is not None:
            meter = conn.execute("select meter_hours from public.assets where id = %s", [aid]).fetchone()["meter_hours"]
            conn.execute(
                """insert into public.measurements (tenant_id, part_item_id, metric, value, unit, source, asset_hours, measured_at)
                   values (%s, %s, 'tread_depth_mm', %s, 'mm', 'import', %s, coalesce(%s::date::timestamptz, now()))""",
                [tenant_id, item, t["tread_mm"], meter, t["measured_at"]])
            created["measurements"] += 1
    return {"created": created, "part_ids": part_ids}


# ---------- Şablon ----------
def template_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Lastikler"
    head_fill = PatternFill("solid", fgColor="0F5B66")
    req_fill = PatternFill("solid", fgColor="17202A")
    for j, c in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=j, value=c.header + (" *" if c.required else ""))
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = req_fill if c.required else head_fill
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[cell.column_letter].width = max(14, len(c.header) + 4)
    examples = [
        ["LD-20", "A1-L", "29.5R25", "Michelin", "radyal", 55, 8, "MX29-1001", 11800, 0, 41, "15.10.2026", 9800, "Volvo", "L220H", "yükleyici", 12500],
        ["LD-20", "A1-R", "29.5R25", "Michelin", None, None, None, "MX29-1002", 11800, 0, 40.5, "15.10.2026", None, None, None, None, None],
        ["LD-20", "A2-L", "29.5R25", "Michelin", None, None, None, "MX29-1003", 9600, 1200, 22, "15.10.2026", None, None, None, None, None],
    ]
    for i, ex in enumerate(examples, start=2):
        for j, v in enumerate(ex, start=1):
            ws.cell(row=i, column=j, value=v)
    ws.row_dimensions[1].height = 34
    ws.freeze_panes = "A2"
    yapi = DataValidation(type="list", formula1='"radyal,diyagonal,dolgu"', allow_blank=True)
    tip = DataValidation(type="list", formula1='"yükleyici,reach stacker,forklift"', allow_blank=True)
    ws.add_data_validation(yapi)
    ws.add_data_validation(tip)
    col = {c.key: i for i, c in enumerate(COLUMNS, start=1)}
    from openpyxl.utils import get_column_letter
    yapi.add(f"{get_column_letter(col['construction'])}2:{get_column_letter(col['construction'])}{MAX_ROWS + 1}")
    tip.add(f"{get_column_letter(col['asset_type'])}2:{get_column_letter(col['asset_type'])}{MAX_ROWS + 1}")

    info = wb.create_sheet("Açıklama")
    info.append(["Sütun", "Zorunlu", "Açıklama", "Örnek"])
    for cell in info[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
    for c in COLUMNS:
        info.append([c.header, "Evet" if c.required else "", c.help, c.example])
    info.append([])
    info.append(["Notlar", "", "Örnek satırları silip kendi listenizi yapıştırın. Aynı ebat + marka için yapı ve diş bilgisini bir kez yazmanız yeterli. "
                 "Yeni makine için makine sütunlarını yalnızca o makinenin ilk satırında doldurun. Yükleyince önce önizleme gösterilir; onaylamadan hiçbir şey kaydedilmez.", ""])
    for letter, w in (("A", 26), ("B", 10), ("C", 90), ("D", 18)):
        info.column_dimensions[letter].width = w
    for row in info.iter_rows(min_row=2):
        row[2].alignment = Alignment(wrap_text=True, vertical="top")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
