"""Maliyet raporunun (TCO) Excel ve PDF çıktısı.

Girdi, /reports/tco'nun döndürdüğü raporun kendisidir (api/tco.py); burada hesap yapılmaz,
yalnızca düzenlenir ve çizilir. PDF, durum raporunun (report.py) yazı tipi, tablo ve sayfa düzenini kullanır.
"""

from __future__ import annotations

import io
from datetime import timedelta
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .report import INK, MUTED, SURF2, TZ, _fonts, _n, _NumberedCanvas, _styles, _table, _usd

TITLE = "Makine toplam sahip olma maliyeti"
# Kalemlerin sırası ve rengi arayüzdekiyle aynı (lib/tco.ts, --tco-1..5 açık tema)
ITEMS = (("parts_cost", "Parça", "#2a78d6"), ("consumables_cost", "Sarf", "#eb6834"), ("labor_cost", "İşçilik", "#1baf7a"),
         ("external_cost", "Dış servis", "#eda100"), ("downtime_cost", "Duruş", "#e87ba4"))
STATUS_TR = {"active": "Aktif", "down": "Arızalı", "maintenance": "Bakımda", "retired": "Hizmet dışı"}
PARTIAL = timedelta(days=7)  # saat kaydı dönem başından bu kadar sonra başlıyorsa "eksik" (arayüzle aynı)


def _d(v) -> str:
    return v.astimezone(TZ).strftime("%d.%m.%Y") if v else "–"


def _dur(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return "–" if not minutes else f"{_n(h)} sa" + (f" {m} dk" if m else "")


def _money(v: Any) -> str:
    """Tam dolar; sıfır yerine tire (tablo sade kalsın)."""
    return "–" if not v else "$" + _n(v)


def _partial(row: dict, rep: dict) -> bool:
    return row["cost_per_hour"] is not None and row["hours_from"] is not None and row["hours_from"] - rep["from"] > PARTIAL


def _scope(rep: dict) -> str:
    return f"{_d(rep['from'])} – {_d(rep['to'])} · {rep['site'] or 'Tüm sahalar'}"


# ---------- Excel ----------
def xlsx(rep: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Maliyet"
    cur = rep["currency"]
    ws["A1"] = f"{rep['tenant']} · {TITLE}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = (f"Dönem: {_scope(rep)} · Para birimi: {cur} · Firma duruş saat maliyeti: {_n(rep['downtime_cost_per_hour'], 2)}"
                f" · Hazırlayan: {rep['user']} · {rep['to'].astimezone(TZ).strftime('%d.%m.%Y %H:%M')}")
    ws["A2"].font = Font(color="55616D")

    cols = [  # başlık, genişlik, sayı biçimi
        ("Makine", 12, None), ("Model", 24, None), ("Saha", 22, None), ("Durum", 12, None),
        ("Parça", 14, "#,##0.00"), ("Sarf", 14, "#,##0.00"), ("İşçilik", 14, "#,##0.00"), ("Dış servis", 14, "#,##0.00"),
        ("Duruş (saat)", 13, "#,##0.0"), ("Duruş saat maliyeti", 18, "#,##0.00"), ("Duruş maliyeti", 15, "#,##0.00"),
        ("Toplam", 15, "#,##0.00"), ("Çalışma saati", 14, "#,##0.0"), ("Saat başı maliyet", 17, "#,##0.00"),
        ("Planlı bakım", 13, "0"), ("Arıza", 9, "0"), ("Saat kaydı başlangıcı", 20, None),
    ]
    head = 4
    for i, (title, width, _) in enumerate(cols, start=1):
        c = ws.cell(row=head, column=i, value=title)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F5B66")
        c.alignment = Alignment(horizontal="left" if i <= 4 else "right", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = width

    def line(r: int, values: list[Any], bold: bool = False) -> None:
        for i, v in enumerate(values, start=1):
            c = ws.cell(row=r, column=i, value=v)
            if cols[i - 1][2]:
                c.number_format = cols[i - 1][2]
            if bold:
                c.font = Font(bold=True)

    f = lambda v: None if v is None else float(v)  # noqa: E731
    r = head
    for a in rep["assets"]:
        r += 1
        line(r, [a["asset_code"], a["model_name"], a["site_name"], STATUS_TR.get(a["asset_status"], a["asset_status"]),
                 f(a["parts_cost"]), f(a["consumables_cost"]), f(a["labor_cost"]), f(a["external_cost"]),
                 round(a["downtime_minutes"] / 60, 2), f(a["downtime_rate"]), f(a["downtime_cost"]), f(a["total"]),
                 f(a["hours_worked"]), f(a["cost_per_hour"]), a["planned_done"], a["breakdowns"],
                 # Yalnızca dönem başını kapsamıyorsa yazılır: saat başı maliyet o zaman eksik saate bölünmüştür
                 _d(a["hours_from"]) if _partial(a, rep) else None])
    t = rep["totals"]
    line(r + 1, ["Filo", None, None, None, f(t["parts_cost"]), f(t["consumables_cost"]), f(t["labor_cost"]), f(t["external_cost"]),
                 round(t["downtime_minutes"] / 60, 2), None, f(t["downtime_cost"]), f(t["total"]), f(t["hours_worked"]),
                 f(t["cost_per_hour"]), sum(a["planned_done"] for a in rep["assets"]), sum(a["breakdowns"] for a in rep["assets"]), None],
         bold=True)
    ws.freeze_panes = ws.cell(row=head + 1, column=2)
    ws.auto_filter.ref = f"A{head}:{get_column_letter(len(cols))}{max(r, head)}"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- PDF ----------
def _share_bar(totals: dict, width: float) -> Drawing:
    """Filo dağılımı: yığılmış tek çubuk + altında etiketli gösterge (renk tek başına anlam taşımaz)."""
    segs = [(label, float(totals[key]), colors.HexColor(color)) for key, label, color in ITEMS if totals[key] > 0]
    total = sum(v for _, v, _ in segs) or 1
    labels = [f"{label} {_money(v)} · {'%' + _n(v / total * 100) if v / total >= 0.01 else '<%1'}" for label, v, _ in segs]
    # Gösterge satırlara sığdığı kadar dizilir
    rows, x = 1, 0.0
    places = []
    for text in labels:
        w = 12 + stringWidth(text, "Barlow-Regular", 8.5) + 14
        if x and x + w > width:
            rows, x = rows + 1, 0.0
        places.append((x, rows))
        x += w
    bar_h, row_h = 10, 13
    h = bar_h + 6 + rows * row_h
    d = Drawing(width, h)
    gap = 1.5
    x = 0.0
    for _, v, color in segs:
        w = (width - gap * (len(segs) - 1)) * v / total
        d.add(Rect(x, h - bar_h, max(w, 0.8), bar_h, fillColor=color, strokeColor=None))
        x += w + gap
    for (lx, row), text, (_, _, color) in zip(places, labels, segs):
        y = h - bar_h - 6 - row * row_h + 3
        d.add(Rect(lx, y, 7, 7, fillColor=color, strokeColor=None))
        d.add(String(lx + 11, y + 0.5, text, fontName="Barlow-Regular", fontSize=8.5, fillColor=INK))
    return d


def pdf(rep: dict[str, Any]) -> bytes:
    _fonts()
    st = _styles()
    W = A4[0] - 32 * mm
    t, rows = rep["totals"], rep["assets"]
    rate = rep["downtime_cost_per_hour"]
    own = [a for a in rows if a["downtime_rate_own"]]
    top = next((a for a in rows if a["total"] > 0), None)
    story: list[Any] = [
        Paragraph(TITLE, st["h1"]), Spacer(1, 1.5 * mm),
        Paragraph(f"{rep['tenant']} · {_scope(rep)} · {rep['to'].astimezone(TZ).strftime('%d.%m.%Y %H:%M')} · Hazırlayan: {rep['user']}",
                  st["muted"]),
        Spacer(1, 6 * mm),
    ]

    def kpi(value: str, label: str):
        return [Paragraph(value, st["kpi"]), Paragraph(label, st["kpil"])]
    cells = [
        kpi(_money(t["total"]), f"toplam maliyet · {_n(len(rows))} makine"),
        kpi(_usd(t["cost_per_hour"]), f"saat başı · {_n(t['hours_worked'])} çalışma saati"),
        kpi(_dur(t["downtime_minutes"]), f"duruş · {_money(t['downtime_cost'])}" if t["downtime_cost"] else "duruş"),
        kpi(top["asset_code"] if top else "–", f"en yüksek maliyet · {_money(top['total'])}" if top else "en yüksek maliyet"),
    ]
    kt = Table([cells], colWidths=[W / 4] * 4)
    kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SURF2), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LINEAFTER", (0, 0), (-2, -1), 2, colors.white)]))
    story += [kt]

    if not top:
        story += [Spacer(1, 4 * mm), Paragraph("Bu dönemde makinelere yazılmış maliyet yok.", st["body"])]
    else:
        story += [Paragraph("Maliyet dağılımı", st["h2"]), _share_bar(t, W - 12)]  # çerçeve iç boşluğu: tabloyla aynı hizada bitsin
        story += [Paragraph("Makineler", st["h2"])]
        table = [["Makine", "Parça", "Sarf", "İşçilik", "Dış servis", "Duruş", "Duruş maliyeti", "Toplam", "Saat başı"]]
        any_partial = False
        for a in rows:
            partial = _partial(a, rep)
            any_partial = any_partial or partial
            sub = " · ".join(x for x in (a["model_name"], a["site_name"]) if x)
            mark = f'<br/><font size="7.5" color="#{MUTED.hexval()[2:]}">'
            table.append([
                Paragraph(f"<b>{a['asset_code']}</b>{mark}{sub}</font>", st["cell"]),
                _money(a["parts_cost"]), _money(a["consumables_cost"]), _money(a["labor_cost"]), _money(a["external_cost"]),
                _dur(a["downtime_minutes"]),
                Paragraph(_money(a["downtime_cost"]) + (f"{mark}${_n(a['downtime_rate'])}/saat</font>"
                                                        if a["downtime_rate_own"] and a["downtime_minutes"] else ""), st["cellr"]),
                Paragraph(f"<b>{_money(a['total'])}</b>", st["cellr"]),
                Paragraph((_usd(a["cost_per_hour"]) + ("*" if partial else "")) + f"{mark}{_n(a['hours_worked'])} saat</font>", st["cellr"]),
            ])
        table.append(["Filo", _money(t["parts_cost"]), _money(t["consumables_cost"]), _money(t["labor_cost"]), _money(t["external_cost"]),
                      _dur(t["downtime_minutes"]), _money(t["downtime_cost"]), _money(t["total"]), _usd(t["cost_per_hour"])])
        tbl = _table(table, [W * x for x in (.18, .1, .08, .08, .1, .09, .14, .11, .12)])
        tbl.setStyle(TableStyle([("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                                 ("FONT", (0, -1), (-1, -1), "Barlow-SemiBold", 8.8),
                                 ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK), ("BACKGROUND", (0, -1), (-1, -1), colors.white)]))
        story += [tbl]

    note = ("Parçanın alış maliyeti ilk takıldığı makineye ve takıldığı güne yazılır; sarf, stok defterinden makineye yapılan "
            "çıkışlardır (iş emirleri dahil). Süren arızaların duruşu rapor anına kadar sayılır. ")
    if rate > 0 or own:
        note += f"Duruş maliyeti = duruş süresi × duruş saat maliyeti (firma: ${_n(rate, 2)}/saat"
        note += f"; {', '.join(a['asset_code'] for a in own)} kendi oranıyla). " if own else "). "
    else:
        note += "Duruş saat maliyeti girilmediği için duruş toplamı etkilemiyor. "
    if top and any_partial:
        note += "* Saat kaydı dönemin tamamını kapsamıyor; saat başı maliyet olduğundan yüksek görünür. "
    note += "Tutarlar tam dolara yuvarlanmıştır; kuruşlu değerler Excel çıktısındadır."
    story += [Spacer(1, 5 * mm), Paragraph(note, st["muted"])]

    buf = io.BytesIO()
    header = f"{rep['tenant']} · {TITLE} · {_d(rep['to'])}"
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                            bottomMargin=15 * mm, title=TITLE, author="SpareTwin", subject=rep["tenant"])
    doc.build(story, canvasmaker=lambda *a, **kw: _NumberedCanvas(*a, header=header, **kw))
    return buf.getvalue()
