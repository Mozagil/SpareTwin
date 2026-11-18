"""Ürün ağacı (üretim BOM'u).

Firmanın ürettiği katalog kalemi hangi kalemlerden, kaçar birim oluşur. Bileşenin kendi
ürün ağacı varsa alt montajdır; ağaç çok seviyeli açılır ve malzeme maliyeti yapraklardan
yukarı toplanır. Elle ya da Excel'den yazılır. Yetki: manager ve üstü.
"""

import io
from decimal import Decimal, InvalidOperation
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from pydantic import BaseModel, Field

from .deps import TenantCtx

router = APIRouter(prefix="/production/boms", tags=["Üretim"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000
HEADERS = ["Ürün parça no", "Bileşen parça no", "Miktar", "Not"]
# Başlık eş anlamlıları (küçük harf, boşluksuz karşılaştırılır)
ALIASES = {
    "parent": {"ürünparçano", "urunparcano", "ürün", "urun", "üstparçano", "ustparcano", "üstparça", "mamul", "parent"},
    "part_no": {"bileşenparçano", "bilesenparcano", "bileşen", "bilesen", "parçano", "parcano", "partno", "stokkodu", "component"},
    "qty": {"miktar", "adet", "qty", "quantity"},
    "notes": {"not", "açıklama", "aciklama", "notes"},
}


class BomIn(BaseModel):
    part_id: UUID = Field(description="Üretilen katalog kalemi")
    notes: str | None = Field(None, max_length=300)


class LineIn(BaseModel):
    part_id: UUID = Field(description="Bileşen")
    qty: Decimal = Field(gt=0, le=1_000_000)
    notes: str | None = Field(None, max_length=300)


# ---------- Ortak okuma ----------
def _parts(conn, tenant_id: UUID) -> dict[UUID, dict]:
    """Firmanın gördüğü katalog: ad, birim, stok ve birim maliyet."""
    return {r["part_id"]: r for r in conn.execute(
        """select part_id, name, part_no, unit, category_code, qty as in_stock, avg_cost
             from public.v_stock_totals where tenant_id = %s""", [tenant_id]).fetchall()}


def _edges(conn, tenant_id: UUID) -> dict[UUID, list[dict]]:
    """Üretilen kalem → bileşen satırları (firmanın bütün ürün ağaçları)."""
    out: dict[UUID, list[dict]] = {}
    for r in conn.execute(
        """select b.part_id as parent_id, l.id, l.part_id, l.qty, l.notes
             from public.boms b
             left join public.bom_lines l on l.bom_id = b.id
            where b.tenant_id = %s order by l.id""", [tenant_id]).fetchall():
        rows = out.setdefault(r["parent_id"], [])
        if r["id"] is not None:
            rows.append(r)
    return out


def _reaches(edges: dict[UUID, list], start: UUID, target: UUID) -> bool:
    """start kaleminin ağacında (kendisi dahil) target var mı?"""
    seen, stack = set(), [start]
    while stack:
        p = stack.pop()
        if p == target:
            return True
        if p not in seen:
            seen.add(p)
            stack.extend(c["part_id"] for c in edges.get(p, []))
    return False


def _unit_cost(part_id: UUID, parts: dict, edges: dict, path: frozenset = frozenset()) -> tuple[Decimal, int]:
    """(1 birimin malzeme maliyeti, maliyeti bilinmeyen yaprak sayısı). Alt montajın maliyeti bileşenlerinden gelir."""
    lines = edges.get(part_id) or []
    if not lines or part_id in path:
        cost = (parts.get(part_id) or {}).get("avg_cost")
        return (Decimal(cost), 0) if cost is not None else (Decimal(0), 1)
    total, unknown = Decimal(0), 0
    for l in lines:
        c, u = _unit_cost(l["part_id"], parts, edges, path | {part_id})
        total += c * l["qty"]
        unknown += u
    return total, unknown


def _tree(part_id: UUID, parts: dict, edges: dict, mult: Decimal, path: frozenset) -> list[dict]:
    out = []
    for l in edges.get(part_id) or []:
        p = parts.get(l["part_id"]) or {}
        cost, unknown = _unit_cost(l["part_id"], parts, edges, path)
        has_bom = bool(edges.get(l["part_id"]))
        total = l["qty"] * mult
        out.append({
            "line_id": l["id"], "part_id": l["part_id"], "name": p.get("name"), "part_no": p.get("part_no"),
            "unit": p.get("unit"), "category_code": p.get("category_code"), "notes": l["notes"],
            "qty": l["qty"], "total_qty": total, "in_stock": p.get("in_stock", 0),
            "unit_cost": None if unknown and not has_bom else cost, "cost": cost * total, "unknown_cost": unknown,
            "has_bom": has_bom,
            "children": _tree(l["part_id"], parts, edges, total, path | {l["part_id"]}) if has_bom and l["part_id"] not in path else [],
        })
    return out


# ---------- Üretilebilirlik ve tedarik açığı ----------
def _net(part_id: UUID, qty: Decimal, edges: dict, stock: dict, used: dict, short: dict, path: frozenset) -> None:
    """qty birim part_id üretmek için ihtiyacı stoktan düşer (stock yerinde azalır).

    Her bileşende önce eldeki stok kullanılır; yetmeyen kısım bileşen alt montajsa onun
    bileşenlerine açılır, satın alınan kalemse eksik (short) yazılır. Aynı kalem ağacın farklı
    dallarında geçiyorsa stok bir kez paylaşılır.
    """
    for l in edges.get(part_id) or []:
        c, need = l["part_id"], l["qty"] * qty
        take = min(stock.get(c, Decimal(0)), need)
        if take > 0:
            stock[c] -= take
            used[c] = used.get(c, Decimal(0)) + take
        rest = need - take
        if rest > 0:
            if edges.get(c) and c not in path:
                _net(c, rest, edges, stock, used, short, path | {c})
            else:
                short[c] = short.get(c, Decimal(0)) + rest


def _shortage(part_id: UUID, qty: Decimal, parts: dict, edges: dict) -> tuple[dict, dict]:
    stock = {pid: Decimal(p["in_stock"]) for pid, p in parts.items() if p["in_stock"] > 0}
    used: dict[UUID, Decimal] = {}
    short: dict[UUID, Decimal] = {}
    _net(part_id, qty, edges, stock, used, short, frozenset({part_id}))
    return used, short


def _can_build(part_id: UUID, parts: dict, edges: dict) -> int:
    """Eldeki stokla, hiçbir şey satın almadan kaç birim üretilir."""
    if not edges.get(part_id):
        return 0
    ok = lambda n: not _shortage(part_id, Decimal(n), parts, edges)[1]  # noqa: E731
    if not ok(1):
        return 0
    lo, hi = 1, 2
    while hi <= 1_000_000 and ok(hi):
        lo, hi = hi, hi * 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


def _bom(conn, bom_id: UUID, tenant_id: UUID) -> dict:
    b = conn.execute("select id, part_id, notes, created_at from public.boms where id = %s and tenant_id = %s",
                     [bom_id, tenant_id]).fetchone()
    if not b:
        raise HTTPException(404, "Ürün ağacı bulunamadı")
    return b


def _detail(conn, b: dict, tenant_id: UUID) -> dict:
    parts, edges = _parts(conn, tenant_id), _edges(conn, tenant_id)
    p = parts.get(b["part_id"]) or {}
    cost, unknown = _unit_cost(b["part_id"], parts, edges)
    return {"id": b["id"], "part_id": b["part_id"], "name": p.get("name"), "part_no": p.get("part_no"), "unit": p.get("unit"),
            "notes": b["notes"], "in_stock": p.get("in_stock", 0), "material_cost": cost, "unknown_cost": unknown,
            # Bu kalem başka hangi ürünlerin içinde geçiyor
            "used_in": [{"part_id": pid, "name": (parts.get(pid) or {}).get("name")}
                        for pid, ls in edges.items() if any(l["part_id"] == b["part_id"] for l in ls)],
            "lines": _tree(b["part_id"], parts, edges, Decimal(1), frozenset({b["part_id"]}))}


def _visible_part(conn, part_id: UUID, tenant_id: UUID) -> None:
    if not conn.execute("select 1 from public.parts where id = %s and (tenant_id is null or tenant_id = %s)",
                        [part_id, tenant_id]).fetchone():
        raise HTTPException(404, "Katalog kalemi bulunamadı")


# ---------- Uçlar ----------
@router.get("", summary="Ürün ağaçları (satır sayısı ve malzeme maliyetiyle)")
def list_boms(ctx: TenantCtx):
    with ctx.tx() as conn:
        parts, edges = _parts(conn, ctx.tenant_id), _edges(conn, ctx.tenant_id)
        out = []
        for b in conn.execute("select id, part_id, notes from public.boms where tenant_id = %s", [ctx.tenant_id]).fetchall():
            p = parts.get(b["part_id"]) or {}
            cost, unknown = _unit_cost(b["part_id"], parts, edges)
            out.append({"id": b["id"], "part_id": b["part_id"], "name": p.get("name"), "part_no": p.get("part_no"),
                        "unit": p.get("unit"), "notes": b["notes"], "line_count": len(edges.get(b["part_id"]) or []),
                        "material_cost": cost, "unknown_cost": unknown,
                        "can_build": _can_build(b["part_id"], parts, edges),
                        # Başka bir ürünün içinde geçiyorsa alt montajdır
                        "is_subassembly": any(l["part_id"] == b["part_id"] for ls in edges.values() for l in ls)})
        return sorted(out, key=lambda r: (r["is_subassembly"], (r["name"] or "").lower()))


@router.post("", status_code=201, summary="Bir katalog kalemi için ürün ağacı aç")
def create_bom(body: BomIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        _visible_part(conn, body.part_id, ctx.tenant_id)
        b = conn.execute(
            """insert into public.boms (tenant_id, part_id, notes, created_by) values (%s, %s, %s, %s)
               on conflict (tenant_id, part_id) do nothing returning id, part_id, notes, created_at""",
            [ctx.tenant_id, body.part_id, body.notes, ctx.user_id]).fetchone()
        if not b:
            raise HTTPException(409, "Bu kalemin ürün ağacı zaten var")
        return _detail(conn, b, ctx.tenant_id)


# ---------- Excel (sabit yollar, /{bom_id} yollarından önce) ----------
@router.get("/template", summary="Ürün ağacı Excel şablonu", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def template(ctx: TenantCtx):
    ctx.require("manager")
    wb = Workbook()
    ws = wb.active
    ws.title = "Ürün ağacı"
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for col, w in zip("ABCD", (24, 24, 10, 40)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    info = wb.create_sheet("Açıklama")
    for line in (
        ["Her satır: bir üründe (ya da alt montajda) bir bileşen."],
        [],
        ["Ürün parça no", "Üretilen kalemin katalogdaki parça numarası (zorunlu)."],
        ["Bileşen parça no", "İçine giren kalemin parça numarası (zorunlu). Kalemler önce Kayıt › Katalog kalemi'nde tanımlı olmalı."],
        ["Miktar", "1 birim ürün için gereken miktar (zorunlu)."],
        ["Not", "İsteğe bağlı."],
        [],
        ["Alt montaj", "Bir bileşenin kendi satırları varsa (Ürün parça no sütununda geçiyorsa) alt montaj olur; aynı dosyada yazılabilir."],
    ):
        info.append(line)
    info.column_dimensions["A"].width = 20
    info.column_dimensions["B"].width = 100
    out = io.BytesIO()
    wb.save(out)
    return Response(out.getvalue(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="sparetwin-urun-agaci.xlsx"'})


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
    if "parent" not in cols or "part_no" not in cols:
        raise HTTPException(422, "“Ürün parça no” ve “Bileşen parça no” sütunları bulunamadı; şablonu indirip onu doldurun")
    if len(rows) - 1 > MAX_ROWS:
        raise HTTPException(422, f"En fazla {MAX_ROWS} satır içe aktarılabilir")
    out = []
    for n, r in enumerate(rows[1:], 2):
        get = lambda f: r[cols[f]] if f in cols and cols[f] < len(r) else None  # noqa: E731
        if all(v is None or str(v).strip() == "" for v in r):
            continue
        out.append({"row": n, "parent": str(get("parent") or "").strip(), "part_no": str(get("part_no") or "").strip(),
                    "qty": get("qty"), "notes": str(get("notes") or "").strip()[:300] or None})
    return out


@router.post("/import", summary="Ürün ağaçlarını Excel'den içe aktar (hata varsa hiçbir satır yazılmaz)")
def import_boms(ctx: TenantCtx, file: Annotated[UploadFile, File(description=".xlsx")]):
    ctx.require("manager")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Dosya en fazla 2 MB olabilir")
    rows = _read(data)
    if not rows:
        raise HTTPException(422, "Dosyada satır yok")
    errors: list[dict] = []
    with ctx.tx() as conn:
        # Aynı parça no hem ortak katalogda hem firmada varsa firmanınki geçerli
        catalog = {}
        for p in conn.execute(
            """select id, lower(part_no) as part_no from public.parts
                where part_no is not null and (tenant_id is null or tenant_id = %s)
                order by tenant_id nulls first""", [ctx.tenant_id]).fetchall():
            catalog[p["part_no"]] = p["id"]
        edges = _edges(conn, ctx.tenant_id)
        graph = {k: [{"part_id": l["part_id"]} for l in v] for k, v in edges.items()}
        plan = []
        for r in rows:
            problems = []
            parent = catalog.get(r["parent"].lower())
            part = catalog.get(r["part_no"].lower())
            if not r["parent"] or not r["part_no"]:
                problems.append("ürün ve bileşen parça no dolu olmalı")
            else:
                if not parent:
                    problems.append(f"{r['parent']}: katalogda bu parça no yok")
                if not part:
                    problems.append(f"{r['part_no']}: katalogda bu parça no yok")
            try:
                qty = Decimal(str(r["qty"]).replace(",", "."))
                if not (0 < qty <= 1_000_000):
                    raise InvalidOperation
            except InvalidOperation:
                problems.append("miktar sıfırdan büyük bir sayı olmalı")
            if not problems and _reaches(graph, part, parent):
                problems.append(f"{r['part_no']} kalemi {r['parent']} ürününü zaten içeriyor (döngü)")
            if problems:
                errors.append({"row": r["row"], "message": "; ".join(problems)})
                continue
            graph.setdefault(parent, []).append({"part_id": part})
            plan.append((parent, part, qty, r["notes"]))
        if errors:
            return {"boms_created": 0, "added": 0, "existing": 0, "errors": errors}
        bom_ids = {r["part_id"]: r["id"] for r in conn.execute(
            "select id, part_id from public.boms where tenant_id = %s", [ctx.tenant_id]).fetchall()}
        created = added = 0
        for parent, part, qty, notes in plan:
            if parent not in bom_ids:
                bom_ids[parent] = conn.execute(
                    "insert into public.boms (tenant_id, part_id, created_by) values (%s, %s, %s) returning id",
                    [ctx.tenant_id, parent, ctx.user_id]).fetchone()["id"]
                created += 1
            added += conn.execute(
                """insert into public.bom_lines (tenant_id, bom_id, part_id, qty, notes) values (%s, %s, %s, %s, %s)
                   on conflict (bom_id, part_id) do nothing""",
                [ctx.tenant_id, bom_ids[parent], part, qty, notes]).rowcount
        return {"boms_created": created, "added": added, "existing": len(plan) - added, "errors": []}


# ---------- Tek ürün ağacı ----------
@router.get("/{bom_id}", summary="Ürün ağacı: çok seviyeli bileşenler, toplam miktar, stok ve malzeme maliyeti")
def get_bom(bom_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        return _detail(conn, _bom(conn, bom_id, ctx.tenant_id), ctx.tenant_id)


@router.get("/{bom_id}/buildable", summary="Üretilebilirlik: eldeki stokla kaç birim çıkar, istenen miktar için ne eksik")
def buildable(bom_id: UUID, ctx: TenantCtx, qty: Decimal = Query(Decimal(1), gt=0, le=1_000_000)):
    with ctx.tx() as conn:
        b = _bom(conn, bom_id, ctx.tenant_id)
        parts, edges = _parts(conn, ctx.tenant_id), _edges(conn, ctx.tenant_id)
        on_order = {r["part_id"]: r["on_order"] or 0 for r in conn.execute(
            "select part_id, on_order from public.v_purchase_on_order where tenant_id = %s", [ctx.tenant_id]).fetchall()}
        used, short = _shortage(b["part_id"], qty, parts, edges)
        lines = []
        for pid in {*used, *short}:
            p = parts.get(pid) or {}
            s, o = short.get(pid, Decimal(0)), Decimal(on_order.get(pid, 0))
            lines.append({"part_id": pid, "name": p.get("name"), "part_no": p.get("part_no"), "unit": p.get("unit"),
                          "has_bom": bool(edges.get(pid)), "required": used.get(pid, Decimal(0)) + s,
                          "in_stock": p.get("in_stock", 0), "on_order": o, "shortage": s,
                          # Yoldaki siparişler gelince de kapanmayan açık
                          "to_buy": max(s - o, Decimal(0))})
        lines.sort(key=lambda r: (r["shortage"] == 0, (r["name"] or "").lower()))
        return {"bom_id": b["id"], "part_id": b["part_id"], "qty": qty,
                "can_build": _can_build(b["part_id"], parts, edges),
                "short_count": len(short), "lines": lines}


@router.delete("/{bom_id}", status_code=204, summary="Ürün ağacını sil (satırlarıyla)")
def delete_bom(bom_id: UUID, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        _bom(conn, bom_id, ctx.tenant_id)
        conn.execute("delete from public.boms where id = %s and tenant_id = %s", [bom_id, ctx.tenant_id])


@router.post("/{bom_id}/lines", status_code=201, summary="Ürün ağacına bileşen ekle")
def add_line(bom_id: UUID, body: LineIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        b = _bom(conn, bom_id, ctx.tenant_id)
        _visible_part(conn, body.part_id, ctx.tenant_id)
        if _reaches(_edges(conn, ctx.tenant_id), body.part_id, b["part_id"]):
            raise HTTPException(422, "Bu kalem ürünün kendisi ya da ürünü içeren bir alt montaj; ağaç döngüye girer")
        cur = conn.execute(
            """insert into public.bom_lines (tenant_id, bom_id, part_id, qty, notes) values (%s, %s, %s, %s, %s)
               on conflict (bom_id, part_id) do nothing""",
            [ctx.tenant_id, bom_id, body.part_id, body.qty, body.notes])
        if cur.rowcount == 0:
            raise HTTPException(409, "Bu bileşen ürün ağacında zaten var")
        return _detail(conn, b, ctx.tenant_id)


@router.delete("/{bom_id}/lines/{line_id}", status_code=204, summary="Ürün ağacından bileşen sil")
def delete_line(bom_id: UUID, line_id: int, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        cur = conn.execute("delete from public.bom_lines where id = %s and bom_id = %s and tenant_id = %s",
                           [line_id, bom_id, ctx.tenant_id])
        if cur.rowcount == 0:
            raise HTTPException(404, "Satır bulunamadı")
