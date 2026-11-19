"""Model parça listesi (kritik parça listesi, BOM).

Makine modelinde hangi yuvaya hangi katalog kalemi uyar; makine genelinde hangi sarf
ve yedek kalemler kullanılır. Liste firmaya aittir ve yol gösterir: takma sırasında
uyumlu parçalar öne çıkar, boş yuvada neyin takılacağı görünür. Yetki: manager ve üstü.
"""

import io
from decimal import Decimal, InvalidOperation
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from pydantic import BaseModel, Field

from .deps import TenantCtx

router = APIRouter(prefix="/catalog/asset-models/{model_id}/bom", tags=["Kütüphane"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 500
HEADERS = ["Parça no", "Yuva", "Miktar", "Not"]
# Başlık eş anlamlıları (küçük harf, boşluksuz karşılaştırılır)
ALIASES = {
    "part_no": {"parçano", "parcano", "partno", "partnumber", "parçanumarası", "stokkodu", "kod"},
    "position": {"yuva", "pozisyon", "position", "konum"},
    "qty": {"miktar", "adet", "qty", "quantity"},
    "notes": {"not", "açıklama", "aciklama", "notes"},
}


class BomLineIn(BaseModel):
    part_id: UUID
    position_code: str | None = Field(None, max_length=24, description="Boşsa makine geneli (sarf / yedek)")
    qty: Decimal = Field(Decimal(1), gt=0, le=100_000)
    notes: str | None = Field(None, max_length=300)


def _model(conn, model_id: UUID, tenant_id: UUID) -> dict:
    m = conn.execute(
        """select id, manufacturer, model, template_id from public.asset_models
            where id = %s and (tenant_id is null or tenant_id = %s)""",
        [model_id, tenant_id],
    ).fetchone()
    if not m:
        raise HTTPException(404, "Makine modeli bulunamadı")
    return m


def _slots(conn, template_id: UUID | None) -> dict[str, dict]:
    if not template_id:
        return {}
    return {r["code"]: r for r in conn.execute(
        "select code, label, category_code from public.template_positions where template_id = %s order by sort_order, code",
        [template_id]).fetchall()}


def _lines(conn, model: dict, tenant_id: UUID) -> list[dict]:
    return conn.execute(
        """select mp.id, mp.part_id, p.name, p.part_no, p.manufacturer, p.unit, pc.code as category_code, pc.is_serialized,
                  mp.position_code, tp.label as position_label, mp.qty, mp.notes,
                  coalesce((select st.qty from public.v_stock_totals st
                             where st.part_id = mp.part_id and st.tenant_id = mp.tenant_id), 0) as in_stock
             from public.model_parts mp
             join public.parts p on p.id = mp.part_id
             join public.part_categories pc on pc.id = p.category_id
             left join public.template_positions tp on tp.template_id = %s and tp.code = mp.position_code
            where mp.model_id = %s and mp.tenant_id = %s
            order by mp.position_code is null, tp.sort_order, mp.position_code, p.name""",
        [model["template_id"], model["id"], tenant_id],
    ).fetchall()


def _check_line(part: dict | None, position: str | None, slots: dict[str, dict]) -> str | None:
    """Satır geçerliyse None, değilse kullanıcıya gösterilecek sebep."""
    if not part:
        return "katalog kalemi bulunamadı"
    if position is None:
        return None
    slot = slots.get(position)
    if not slot:
        return f"{position} yuvası bu modelin şablonunda yok"
    if not part["is_serialized"]:
        return "miktarla izlenen kalem bir yuvaya yazılamaz; yuvayı boş bırakın"
    if slot["category_code"] != part["category_code"]:
        return f"{position} yuvası başka bir parça tipi bekliyor"
    return None


def _insert(conn, ctx: TenantCtx, model_id: UUID, part_id: UUID, position: str | None, qty, notes: str | None) -> bool:
    """Satırı ekler; aynı kalem aynı yuvada zaten varsa False."""
    cur = conn.execute(
        """insert into public.model_parts (tenant_id, model_id, part_id, position_code, qty, notes, created_by)
           values (%s, %s, %s, %s, %s, %s, %s)
           on conflict (tenant_id, model_id, part_id, coalesce(position_code, '')) do nothing""",
        [ctx.tenant_id, model_id, part_id, position, Decimal(1) if position else qty, notes, ctx.user_id],
    )
    return cur.rowcount == 1


@router.get("", summary="Model parça listesi: yuvalara uyan kalemler ve makine geneli sarf / yedek")
def get_bom(model_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        m = _model(conn, model_id, ctx.tenant_id)
        return {"model_id": m["id"], "manufacturer": m["manufacturer"], "model": m["model"],
                "slots": list(_slots(conn, m["template_id"]).values()), "lines": _lines(conn, m, ctx.tenant_id)}


@router.post("", status_code=201, summary="Parça listesine satır ekle")
def add_line(model_id: UUID, body: BomLineIn, ctx: TenantCtx):
    ctx.require("manager")
    position = (body.position_code or "").strip().upper() or None
    with ctx.tx() as conn:
        m = _model(conn, model_id, ctx.tenant_id)
        part = conn.execute(
            """select p.id, pc.code as category_code, pc.is_serialized from public.parts p
                 join public.part_categories pc on pc.id = p.category_id
                where p.id = %s and (p.tenant_id is null or p.tenant_id = %s)""",
            [body.part_id, ctx.tenant_id],
        ).fetchone()
        problem = _check_line(part, position, _slots(conn, m["template_id"]))
        if problem:
            raise HTTPException(404 if not part else 422, problem[0].upper() + problem[1:])
        if not _insert(conn, ctx, model_id, body.part_id, position, body.qty, body.notes):
            raise HTTPException(409, "Bu kalem bu yuva için listede zaten var")
        return _lines(conn, m, ctx.tenant_id)


@router.delete("/{line_id}", status_code=204, summary="Parça listesinden satır sil")
def delete_line(model_id: UUID, line_id: int, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        cur = conn.execute("delete from public.model_parts where id = %s and model_id = %s and tenant_id = %s",
                           [line_id, model_id, ctx.tenant_id])
        if cur.rowcount == 0:
            raise HTTPException(404, "Satır bulunamadı")


# ---------- Excel ----------
@router.get("/template", summary="Parça listesi Excel şablonu (bu modelin yuvalarıyla)",
            response_class=Response, responses={200: {"content": {XLSX: {}}}})
def template(model_id: UUID, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        m = _model(conn, model_id, ctx.tenant_id)
        slots = _slots(conn, m["template_id"])
    wb = Workbook()
    ws = wb.active
    ws.title = "Parça listesi"
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for i, w in enumerate((24, 16, 10, 40), 1):
        ws.column_dimensions["ABCD"[i - 1]].width = w
    ws.freeze_panes = "A2"
    info = wb.create_sheet("Açıklama")
    for line in (
        [f"{m['manufacturer']} {m['model']} parça listesi"],
        [],
        ["Parça no", "Katalogdaki parça numarası (zorunlu). Kalem önce Kayıt › Katalog kalemi'nde tanımlı olmalı."],
        ["Yuva", "Seri numaralı parça için yuva kodu. Sarf (filtre, yağ) ve yedek için boş bırakın."],
        ["Miktar", "Makine başına kullanım. Yuvaya yazılan satırda dikkate alınmaz (1). Boşsa 1."],
        ["Not", "İsteğe bağlı."],
        [],
        ["Bu modelin yuvaları"],
        *[[s["code"], s["label"]] for s in slots.values()],
    ):
        info.append(line)
    info.column_dimensions["A"].width = 18
    info.column_dimensions["B"].width = 90
    out = io.BytesIO()
    wb.save(out)
    return Response(out.getvalue(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="sparetwin-parca-listesi.xlsx"'})


def _key(v) -> str:
    return "".join(str(v or "").lower().split())


def _read(data: bytes) -> list[dict]:
    try:
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    except Exception:  # noqa: BLE001 - bozuk ya da Excel olmayan dosya
        raise HTTPException(422, "Dosya okunamadı; .xlsx biçiminde olmalı")
    rows = list(ws.iter_rows(values_only=True, max_row=MAX_ROWS + 2))
    if not rows:
        raise HTTPException(422, "Dosya boş")
    cols = {}
    for i, h in enumerate(rows[0]):
        for field, names in ALIASES.items():
            if _key(h) in names:
                cols.setdefault(field, i)
    if "part_no" not in cols:
        raise HTTPException(422, "“Parça no” sütunu bulunamadı; şablonu indirip onu doldurun")
    if len(rows) - 1 > MAX_ROWS:
        raise HTTPException(422, f"En fazla {MAX_ROWS} satır içe aktarılabilir")
    out = []
    for n, r in enumerate(rows[1:], 2):
        get = lambda f: r[cols[f]] if f in cols and cols[f] < len(r) else None  # noqa: E731
        if all(v is None or str(v).strip() == "" for v in r):
            continue
        out.append({"row": n, "part_no": str(get("part_no") or "").strip(), "position": str(get("position") or "").strip().upper() or None,
                    "qty": get("qty"), "notes": str(get("notes") or "").strip()[:300] or None})
    return out


@router.post("/import", summary="Parça listesini Excel'den içe aktar (hata varsa hiçbir satır yazılmaz)")
def import_bom(model_id: UUID, ctx: TenantCtx, file: Annotated[UploadFile, File(description=".xlsx")]):
    ctx.require("manager")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Dosya en fazla 2 MB olabilir")
    rows = _read(data)
    if not rows:
        raise HTTPException(422, "Dosyada satır yok")
    errors: list[dict] = []
    with ctx.tx() as conn:
        m = _model(conn, model_id, ctx.tenant_id)
        slots = _slots(conn, m["template_id"])
        # Aynı parça no hem ortak katalogda hem firmada varsa firmanınki geçerli
        catalog = {}
        for p in conn.execute(
            """select p.id, lower(p.part_no) as part_no, pc.code as category_code, pc.is_serialized
                 from public.parts p join public.part_categories pc on pc.id = p.category_id
                where p.part_no is not null and (p.tenant_id is null or p.tenant_id = %s)
                order by p.tenant_id nulls first""", [ctx.tenant_id]).fetchall():
            catalog[p["part_no"]] = p
        plan = []
        for r in rows:
            if not r["part_no"]:
                errors.append({"row": r["row"], "message": "parça no boş"})
                continue
            part = catalog.get(r["part_no"].lower())
            problem = f"{r['part_no']}: katalogda bu parça no yok" if not part else _check_line(part, r["position"], slots)
            try:
                qty = Decimal(str(r["qty"]).replace(",", ".")) if r["qty"] not in (None, "") else Decimal(1)
                if not (0 < qty <= 100_000):
                    raise InvalidOperation
            except InvalidOperation:
                problem = problem or "miktar sıfırdan büyük bir sayı olmalı"
                qty = Decimal(1)
            if problem:
                errors.append({"row": r["row"], "message": problem})
            else:
                plan.append((part["id"], r["position"], qty, r["notes"]))
        if errors:
            return {"added": 0, "existing": 0, "errors": errors}
        added = sum(1 for p in plan if _insert(conn, ctx, model_id, *p))
        return {"added": added, "existing": len(plan) - added, "errors": []}
