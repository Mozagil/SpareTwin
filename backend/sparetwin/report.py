"""PDF durum raporu (filo veya tek makine).

Veri yalnızca veritabanı görünümlerinden okunur (aynı hesaplar, aynı RLS);
burada hesap yapılmaz, sadece düzenlenir ve çizilir.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
from PIL import Image as PILImage
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .storage import Storage

TZ = ZoneInfo("Europe/Istanbul")
FONT_DIR = Path(__file__).parent / "fonts"
_fonts_ready = False


def _fonts() -> None:
    """Barlow (OFL) gömülür: PDF'in standart yazı tiplerinde ş, ğ, İ, ı yoktur."""
    global _fonts_ready
    if _fonts_ready:
        return
    for name in ("Barlow-Regular", "Barlow-SemiBold", "BarlowCondensed-SemiBold", "BarlowCondensed-Bold"):
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f"{name}.ttf")))
    # <b> etiketinin kalın Barlow'a geçmesi için aile tanımı
    pdfmetrics.registerFontFamily("Barlow-Regular", normal="Barlow-Regular", bold="Barlow-SemiBold",
                                  italic="Barlow-Regular", boldItalic="Barlow-SemiBold")
    _fonts_ready = True


# Uygulamadaki renkler (açık tema)
INK = colors.HexColor("#17202A")
MUTED = colors.HexColor("#55616D")
LINE = colors.HexColor("#C8D0D6")
SURF2 = colors.HexColor("#ECEFF1")
BRAND = colors.HexColor("#0F5B66")
BAND = {"ok": colors.HexColor("#2C8A55"), "watch": colors.HexColor("#C08600"),
        "critical": colors.HexColor("#C23F2B"), "unknown": colors.HexColor("#8A949C")}
BAND_TR = {"ok": "İyi", "watch": "Takipte", "critical": "Kritik", "unknown": "Ölçüm yok"}
CAT_TR = {"tire": "Lastik", "rim": "Jant", "hyd_cylinder": "Hidrolik silindir", "hyd_pump": "Hidrolik pompa",
          "battery": "Akü", "filter": "Filtre"}
DUE_HOURS = 500  # "yaklaşan değişim" eşiği


def _n(v: Any, digits: int = 0) -> str:
    if v is None:
        return "–"
    s = f"{float(v):,.{digits}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _usd(v: Any) -> str:
    return "–" if v is None else "$" + _n(v, 2)


def _date(v: datetime | None) -> str:
    return v.astimezone(TZ).strftime("%d.%m.%Y") if v else "–"


# ---------- Veri ----------
@dataclass
class Scope:
    asset_id: UUID | None = None
    site_id: UUID | None = None


def gather(conn: psycopg.Connection, storage: Storage, tenant_id: UUID, user_id: UUID, scope: Scope) -> dict[str, Any]:
    f = {"t": tenant_id, "a": scope.asset_id, "s": scope.site_id}
    where_asset = "(%(a)s::uuid is null or h.id = %(a)s) and (%(s)s::uuid is null or h.site_id = %(s)s)"
    tenant = conn.execute("select name from public.tenants where id = %(t)s", f).fetchone()
    user = conn.execute("select coalesce(full_name, email) as n from public.app_users where id = %s", [user_id]).fetchone()
    assets = conn.execute(
        f"""select h.*, s.name as site_name from public.v_asset_health h
              left join public.sites s on s.id = h.site_id
             where h.tenant_id = %(t)s and {where_asset}
             order by h.critical_parts desc, h.watch_parts desc, h.code""", f).fetchall()
    ids = [a["id"] for a in assets]
    parts = conn.execute(
        """select ph.*, th.tread_mm, th.tread_remaining_pct
             from public.v_part_health ph left join public.v_tire_health th on th.id = ph.id
            where ph.tenant_id = %s and ph.status = 'installed' and ph.current_asset_id = any(%s)""",
        [tenant_id, ids]).fetchall()
    cost = conn.execute(
        """select a.code, count(th.id) as tires, round(sum(th.expected_cost_per_hour), 2) as cph
             from public.assets a join public.v_tire_health th on th.current_asset_id = a.id and th.status = 'installed'
            where a.id = any(%s) group by a.code order by cph desc nulls last""", [ids]).fetchall()
    stock = conn.execute(
        """select p.name, p.min_stock,
                  (select count(*) from public.part_items pi where pi.part_id = p.id and pi.tenant_id = %(t)s
                     and pi.status = 'in_stock') as in_stock
             from public.parts p where (p.tenant_id = %(t)s or p.tenant_id is null) and p.min_stock > 0""", f).fetchall()
    # Jantlar: tek makine raporunda o makinedekiler; filo raporunda takılı olanlar + stoktakiler
    rims = conn.execute(
        """select r.serial_no, r.asset_code, r.current_position, r.compliance, r.hours_since_ndt, r.ndt_interval_hours
             from public.v_rim_compliance r join public.part_items pi on pi.id = r.id
            where r.tenant_id = %s and r.compliance in ('overdue', 'due_soon')
              and (pi.current_asset_id = any(%s) or (%s::uuid is null and pi.current_asset_id is null))""",
        [tenant_id, ids, scope.asset_id]).fetchall()

    attention = sorted(
        [p for p in parts if p["band"] in ("critical", "watch")],
        key=lambda p: (0 if p["band"] == "critical" else 1, p["projected_hours_left"] if p["projected_hours_left"] is not None else 1e9,
                       p["condition_pct"] if p["condition_pct"] is not None else 0))
    tires = [p for p in parts if p["category_code"] == "tire"]
    measured = [p for p in tires if p["tread_remaining_pct"] is not None]

    # Dikkat gerektiren lastiklerin son saha fotoğrafı (taban açısı tercih edilir), en fazla 6.
    # Resmi belge: yalnızca tamamlanmış kontrollerin fotoğrafları (ölçümlerdeki kuralla aynı).
    photos = []
    for p in [x for x in attention if x["category_code"] == "tire"][:6]:
        ph = conn.execute(
            """select a.storage_key, a.angle, a.created_at from public.attachments a
                 join public.inspections i on i.id = a.entity_id and a.entity_type = 'inspection'
                where a.part_item_id = %s and a.kind = 'photo' and a.mime_type like 'image/%%'
                  and i.status = 'completed'
                order by (a.angle = 'tread') desc, a.created_at desc limit 1""", [p["id"]]).fetchone()
        if ph:
            try:
                photos.append({"part": p, "angle": ph["angle"], "at": ph["created_at"], "data": storage.get(ph["storage_key"])})
            except Exception:
                pass  # dosya bulunamazsa rapor yine üretilsin

    return {
        "tenant": tenant["name"], "user": user["n"] if user else "", "now": datetime.now(TZ),
        "single": scope.asset_id is not None, "assets": assets, "attention": attention, "cost": cost,
        "stock": [s for s in stock if s["in_stock"] < s["min_stock"]], "rims": rims, "photos": photos,
        "kpi": {
            "assets": len(assets), "tires": len(tires),
            "critical": sum(1 for p in parts if p["band"] == "critical"),
            "watch": sum(1 for p in parts if p["band"] == "watch"),
            "due": sum(1 for p in tires if p["projected_hours_left"] is not None and p["projected_hours_left"] <= DUE_HOURS),
            "avg_tread": (sum(Decimal(p["tread_remaining_pct"]) for p in measured) / len(measured)) if measured else None,
            "unmeasured": len(tires) - len(measured),
        },
    }


# ---------- Çizim ----------
def _styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName="Barlow-Regular", fontSize=9.5, leading=12.5, textColor=INK)
    return {
        "h1": ParagraphStyle("h1", **{**base, "fontName": "BarlowCondensed-Bold", "fontSize": 24, "leading": 28}),
        "h2": ParagraphStyle("h2", **{**base, "fontName": "BarlowCondensed-SemiBold", "fontSize": 15, "leading": 19,
                                      "spaceBefore": 10, "spaceAfter": 5}),
        "body": ParagraphStyle("body", **base),
        "muted": ParagraphStyle("muted", **{**base, "textColor": MUTED, "fontSize": 8.5, "leading": 11}),
        "cell": ParagraphStyle("cell", **{**base, "fontSize": 8.8, "leading": 11}),
        "cellr": ParagraphStyle("cellr", **{**base, "fontSize": 8.8, "leading": 11, "alignment": TA_RIGHT}),
        "kpi": ParagraphStyle("kpi", **{**base, "fontName": "BarlowCondensed-Bold", "fontSize": 22, "leading": 24}),
        "kpil": ParagraphStyle("kpil", **{**base, "fontSize": 8.2, "leading": 10, "textColor": MUTED}),
    }


def _band(b: str, text: str | None = None) -> str:
    c = BAND.get(b, BAND["unknown"]).hexval()[2:]
    return f'<font color="#{c}"><b>{text or BAND_TR.get(b, b)}</b></font>'


def _table(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONT", (0, 0), (-1, -1), "Barlow-Regular", 8.8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
    ]
    if header:
        style += [("FONT", (0, 0), (-1, 0), "Barlow-SemiBold", 8.2), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                  ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK)]
    for i in range(1 if header else 0, len(rows)):
        if (i % 2 == 0) == header:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F5F7F8")))
    t.setStyle(TableStyle(style))
    return t


def _cost_chart(rows: list[dict], width: float) -> Drawing:
    rows = [r for r in rows if r["cph"] is not None]
    h = 16 * len(rows) + 6
    d = Drawing(width, h)
    mx = max((float(r["cph"]) for r in rows), default=1) or 1
    label_w, val_w = 52, 52
    bar_w = width - label_w - val_w
    for i, r in enumerate(rows):
        y = h - 16 * (i + 1)
        d.add(String(0, y + 3, r["code"], fontName="BarlowCondensed-SemiBold", fontSize=10, fillColor=INK))
        d.add(Rect(label_w, y + 2, bar_w, 8, fillColor=SURF2, strokeColor=None))
        d.add(Rect(label_w, y + 2, bar_w * float(r["cph"]) / mx, 8, fillColor=BRAND, strokeColor=None))
        d.add(String(width, y + 3, _usd(r["cph"]), fontName="Barlow-Regular", fontSize=9, fillColor=INK, textAnchor="end"))
    return d


def _thumb(data: bytes, max_w: float, max_h: float) -> Image:
    im = PILImage.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((700, 700))  # PDF'i küçük tut
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=78)
    buf.seek(0)
    w, h = im.size
    scale = min(max_w / w, max_h / h)
    return Image(buf, width=w * scale, height=h * scale)


class _NumberedCanvas(rl_canvas.Canvas):
    """Her sayfaya başlık ve 'Sayfa x / y' (toplam sayfa sayısı sonradan bilinir)."""

    def __init__(self, *a, header: str = "", **k):
        super().__init__(*a, **k)
        self._pages: list[dict] = []
        self._header = header

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._decorate(total)
            super().showPage()
        super().save()

    def _decorate(self, total: int):
        w, h = A4
        self.setFont("Barlow-Regular", 7.8)
        self.setFillColor(MUTED)
        self.drawString(16 * mm, h - 10 * mm, self._header)
        self.drawRightString(w - 16 * mm, 8 * mm, f"Sayfa {self._pageNumber} / {total}")
        self.drawString(16 * mm, 8 * mm, "SpareTwin · Gizli: yalnızca firma içi kullanım")
        self.setStrokeColor(LINE)
        self.setLineWidth(0.4)
        self.line(16 * mm, h - 11.5 * mm, w - 16 * mm, h - 11.5 * mm)


def render(d: dict[str, Any]) -> bytes:
    _fonts()
    st = _styles()
    W = A4[0] - 32 * mm
    k = d["kpi"]
    title = (f"{d['assets'][0]['code']} makine durum raporu" if d["single"] and d["assets"] else "Filo durum raporu")
    story: list[Any] = [
        Paragraph(title, st["h1"]),
        Paragraph(f"{d['tenant']} · {d['now'].strftime('%d.%m.%Y %H:%M')} · Hazırlayan: {d['user']}", st["muted"]),
        Spacer(1, 6 * mm),
    ]

    # Yönetici özeti
    def kpi(value: str, label: str, color=INK):
        return [Paragraph(f'<font color="#{color.hexval()[2:]}">{value}</font>', st["kpi"]), Paragraph(label, st["kpil"])]
    cells = [
        kpi(_n(k["assets"]), "makine"),
        kpi(_n(k["tires"]), "takılı lastik"),
        kpi(_n(k["critical"]), "kritik parça", BAND["critical"] if k["critical"] else INK),
        kpi(_n(k["watch"]), "takipteki parça", BAND["watch"] if k["watch"] else INK),
        kpi(_n(k["due"]), f"{DUE_HOURS} saat içinde değişecek lastik"),
        kpi("%" + _n(k["avg_tread"]) if k["avg_tread"] is not None else "–", "ortalama kalan diş"),
    ]
    kt = Table([cells], colWidths=[W / 6] * 6)
    kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SURF2), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LINEAFTER", (0, 0), (-2, -1), 2, colors.white)]))
    story += [kt]
    if k["unmeasured"]:
        story += [Spacer(1, 2 * mm), Paragraph(
            f"{k['unmeasured']} lastiğin henüz diş ölçümü yok; bu lastikler ortalamaya ve tahminlere dahil değil.", st["muted"])]

    # Makineler
    story += [Paragraph("Makineler" if not d["single"] else "Makine", st["h2"])]
    if not d["assets"]:
        story += [Paragraph("Henüz makine kaydı yok.", st["body"])]
    else:
        rows = [["Makine", "Model", "Saha", "Motor saati", "Son kontrol", "Kritik", "Takipte", "En kötü"]]
        for a in d["assets"]:
            worst = a["worst_condition_pct"]
            wb = "critical" if worst is not None and worst < 20 else "watch" if worst is not None and worst < 40 else "ok"
            rows.append([
                Paragraph(f"<b>{a['code']}</b>", st["cell"]), Paragraph(f"{a['manufacturer'] or ''} {a['model'] or ''}", st["cell"]),
                Paragraph(a["site_name"] or "–", st["cell"]), Paragraph(_n(a["meter_hours"]), st["cellr"]),
                _date(a["last_inspection_at"]),
                Paragraph(_band("critical", str(a["critical_parts"])) if a["critical_parts"] else "0", st["cellr"]),
                Paragraph(_band("watch", str(a["watch_parts"])) if a["watch_parts"] else "0", st["cellr"]),
                Paragraph(_band(wb, "%" + _n(worst)) if worst is not None else "–", st["cellr"]),
            ])
        story += [_table(rows, [W * x for x in (.11, .19, .2, .11, .12, .08, .09, .1)])]

    # Öncelikli işler
    story += [Paragraph("Öncelikli işler", st["h2"])]
    if not d["attention"]:
        story += [Paragraph("Takip gerektiren parça yok.", st["body"])]
    else:
        rows = [["Durum", "Makine · pozisyon", "Parça", "Seri no", "Diş / ömür", "Kalan saat"]]
        for p in d["attention"][:25]:
            is_tire = p["category_code"] == "tire"
            remaining = (f"diş %{_n(p['condition_pct'])}" + (f" ({_n(p['tread_mm'], 1)} mm)" if p["tread_mm"] is not None else "")
                         if is_tire else ("ömrü aştı" if (p["condition_pct"] or 0) <= 0 else f"ömür %{_n(p['condition_pct'])}"))
            rows.append([
                Paragraph(_band(p["band"]), st["cell"]),
                Paragraph(f"<b>{p['asset_code']}</b> {p['current_position']}", st["cell"]),
                Paragraph(f"{CAT_TR.get(p['category_code'], p['category_code'])} · {p['part_name']}", st["cell"]),
                Paragraph(p["serial_no"] or "–", st["cell"]),
                Paragraph(remaining, st["cell"]),
                Paragraph(f"{_n(p['projected_hours_left'])} sa" if p["projected_hours_left"] is not None else "–", st["cellr"]),
            ])
        story += [_table(rows, [W * x for x in (.09, .16, .33, .14, .16, .12)])]
        if len(d["attention"]) > 25:
            story += [Paragraph(f"…ve {len(d['attention']) - 25} parça daha. Tam liste uygulamada.", st["muted"])]

    # Maliyet
    if d["cost"]:
        story += [KeepTogether([
            Paragraph("Lastik maliyeti, saat başına", st["h2"]),
            Paragraph("Makinedeki tüm lastikler; maliyet ÷ (çalıştığı saat + ölçülen aşınma hızıyla kalan saat).", st["muted"]),
            Spacer(1, 2 * mm), _cost_chart(d["cost"], W)])]

    # Jant ve stok uyarıları
    if d["rims"]:
        rows = [["Jant", "Konum", "Durum", "Son muayeneden bu yana"]]
        for r in d["rims"]:
            rows.append([r["serial_no"] or "–", f"{r['asset_code'] or 'stok'} {r['current_position'] or ''}",
                         Paragraph(_band("critical", "Gecikmiş") if r["compliance"] == "overdue" else _band("watch", "Yaklaşıyor"), st["cell"]),
                         f"{_n(r['hours_since_ndt'])} / {_n(r['ndt_interval_hours'])} saat"])
        story += [KeepTogether([Paragraph("Jant muayenesi (NDT)", st["h2"]), _table(rows, [W * x for x in (.2, .25, .2, .35)])])]
    if d["stock"] and not d["single"]:
        rows = [["Katalog kalemi", "Depoda", "Kritik seviye"]]
        rows += [[Paragraph(s["name"], st["cell"]), Paragraph(_band("watch", str(s["in_stock"])), st["cellr"]),
                  Paragraph(str(s["min_stock"]), st["cellr"])] for s in d["stock"]]
        story += [KeepTogether([Paragraph("Stok uyarıları", st["h2"]), _table(rows, [W * .6, W * .2, W * .2])])]

    # Fotoğraflar
    if d["photos"]:
        col_w = W / 3 - 4 * mm
        cells, row = [], []
        for ph in d["photos"]:
            p = ph["part"]
            cap = Paragraph(f"<b>{p['asset_code']} {p['current_position']}</b> · {_band(p['band'], '%' + _n(p['condition_pct']))}"
                            f"<br/>{'Taban' if ph['angle'] == 'tread' else 'Yanak' if ph['angle'] == 'sidewall' else 'Fotoğraf'}"
                            f" · {_date(ph['at'])}", st["cell"])
            row.append([_thumb(ph["data"], col_w - 4, 52 * mm), cap])
            if len(row) == 3:
                cells.append(row)
                row = []
        if row:
            cells.append(row + [""] * (3 - len(row)))
        t = Table(cells, colWidths=[W / 3] * 3, hAlign="LEFT")
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        # Başlık sayfa sonunda yalnız kalmasın: başlık ve ilk fotoğraf sırası birlikte
        story += [KeepTogether([Paragraph("Dikkat gerektiren lastiklerin son saha fotoğrafları", st["h2"]), t])]

    story += [Spacer(1, 6 * mm), Paragraph(
        "Kalan ömür tahminleri, son ölçümlere göre doğrusal aşınma varsayımıyla hesaplanır; zemin, yük ve basınç koşulları "
        "değiştikçe sapabilir. Tahminler değişim planlamasına yardımcı olmak içindir; güvenlik kararları için lastiğin "
        "yerinde kontrolü esastır.", st["muted"])]

    buf = io.BytesIO()
    header = f"{d['tenant']} · {title} · {d['now'].strftime('%d.%m.%Y')}"
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                            bottomMargin=15 * mm, title=title, author="SpareTwin", subject=d["tenant"])
    doc.build(story, canvasmaker=lambda *a, **kw: _NumberedCanvas(*a, header=header, **kw))
    return buf.getvalue()
