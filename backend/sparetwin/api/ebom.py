"""Mühendislik ağacı (eBOM) ve eBOM → mBOM kuralları (0025).

eBOM tasarımın ağacıdır; üretimin kullandığı ürün ağacı (mBOM, api/production.py)
ondan firmanın kurallarıyla türetilir. Dönüşüm saklanmaz: eBOM ayrıntısı her
açılışta "kurallar uygulanınca mBOM böyle olur" önizlemesini ve bugünkü ürün
ağacıyla farkını döner; ürün ağacı yalnızca `apply` ile güncellenir.
Yetki: yazma manager ve üstü.
"""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator

from ..ebom import convert
from .deps import TenantCtx
from .production import EBOM, LineIn, BomIn, _edges, _parts, _reaches, _visible_part, import_file

router = APIRouter(prefix="/production", tags=["Üretim"])

ACTION_LABEL = {"flatten": "Düzleştir", "exclude": "Çıkar", "substitute": "Değiştir", "add": "Sarf ekle", "scrap": "Fire payı"}


class RuleIn(BaseModel):
    action: Literal["flatten", "exclude", "substitute", "add", "scrap"]
    match_part_id: UUID | None = Field(None, description="Tek kalem")
    match_category: str | None = Field(None, max_length=40, description="Parça tipi kodu")
    target_part_id: UUID | None = Field(None, description="Değiştir: yerine geçen; sarf ekle: eklenen kalem")
    qty: Decimal | None = Field(None, gt=0, le=1_000_000, description="Değiştir: oran; sarf ekle: miktar")
    per: Literal["product", "match"] | None = Field(None, description="Sarf ekle: ürün başına / eşleşen birim başına")
    scrap_pct: Decimal | None = Field(None, gt=0, le=100)

    @model_validator(mode="after")
    def _check(self):
        if self.match_part_id and self.match_category:
            raise ValueError("Eşleşme tek kalem ya da parça tipi olabilir, ikisi birden olmaz")
        matched = bool(self.match_part_id or self.match_category)
        if self.action == "scrap":
            if self.scrap_pct is None:
                raise ValueError("Fire payı için yüzde gerekli")
        elif self.action == "substitute":
            if not self.match_part_id or not self.target_part_id:
                raise ValueError("Değiştirme için hangi kalemin yerine hangisinin geçeceği gerekli")
            if self.match_part_id == self.target_part_id:
                raise ValueError("Kalem kendisiyle değiştirilemez")
            self.qty = self.qty or Decimal(1)
        elif self.action == "add":
            if not self.target_part_id or self.qty is None:
                raise ValueError("Sarf ekleme için eklenecek kalem ve miktar gerekli")
            self.per = self.per or "product"
            if self.per == "match" and not matched:
                raise ValueError("Birim başına ekleme için eşleşecek kalem ya da parça tipi seçin")
        elif not matched:
            raise ValueError("Bu kural için eşleşecek kalem ya da parça tipi seçin")
        # Tipe ait olmayan alanlar yazılmaz
        if self.action != "scrap":
            self.scrap_pct = None
        if self.action not in ("substitute", "add"):
            self.target_part_id = self.qty = None
        if self.action != "add":
            self.per = None
        return self


class RulePatch(BaseModel):
    is_active: bool


# ---------- Kurallar ----------
def _num(v: Decimal) -> str:
    return f"{v.normalize():f}".replace(".", ",")


def _rules(conn, tenant_id: UUID, parts: dict) -> list[dict]:
    cats = {r["code"]: r["name"] for r in conn.execute(
        """select code, name from public.part_categories
            where tenant_id is null or tenant_id = %s order by tenant_id nulls first""", [tenant_id]).fetchall()}
    rows = conn.execute(
        """select id, action, match_part_id, match_category, target_part_id, qty, per, scrap_pct, is_active
             from public.bom_rules where tenant_id = %s order by created_at, id""", [tenant_id]).fetchall()
    name = lambda pid: (parts.get(pid) or {}).get("name") or "silinmiş kalem"  # noqa: E731
    for r in rows:
        r["match_name"] = (name(r["match_part_id"]) if r["match_part_id"]
                           else cats.get(r["match_category"], r["match_category"]) if r["match_category"] else None)
        r["target_name"] = name(r["target_part_id"]) if r["target_part_id"] else None
        r["target_unit"] = (parts.get(r["target_part_id"]) or {}).get("unit") if r["target_part_id"] else None
        who = r["match_name"] or "tüm kalemler"
        if r["action"] == "scrap":
            r["label"] = f"Fire payı %{_num(r['scrap_pct'])} · {who}"
        elif r["action"] == "substitute":
            ratio = "" if r["qty"] == 1 else f" × {_num(r['qty'])}"
            r["label"] = f"Değiştir · {who} → {r['target_name']}{ratio}"
        elif r["action"] == "add":
            per = "ürün başına" if r["per"] == "product" else f"her {who} için"
            scope = f" ({who} içeren ürünlerde)" if r["per"] == "product" and r["match_name"] else ""
            r["label"] = f"Sarf ekle · {r['target_name']} {_num(r['qty'])} {r['target_unit'] or ''} {per}{scope}".replace("  ", " ")
        else:
            r["label"] = f"{ACTION_LABEL[r['action']]} · {who}"
    return rows


@router.get("/bom-rules", summary="eBOM → mBOM kuralları")
def list_rules(ctx: TenantCtx):
    with ctx.tx() as conn:
        return _rules(conn, ctx.tenant_id, _parts(conn, ctx.tenant_id))


@router.post("/bom-rules", status_code=201, summary="Kural ekle")
def create_rule(body: RuleIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        for pid in (body.match_part_id, body.target_part_id):
            if pid:
                _visible_part(conn, pid, ctx.tenant_id)
        if body.match_category and not conn.execute(
            "select 1 from public.part_categories where code = %s and (tenant_id is null or tenant_id = %s)",
            [body.match_category, ctx.tenant_id],
        ).fetchone():
            raise HTTPException(404, f"Parça tipi bulunamadı: {body.match_category}")
        rid = conn.execute(
            """insert into public.bom_rules
                 (tenant_id, action, match_part_id, match_category, target_part_id, qty, per, scrap_pct, created_by)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
            [ctx.tenant_id, body.action, body.match_part_id, body.match_category, body.target_part_id,
             body.qty, body.per, body.scrap_pct, ctx.user_id]).fetchone()["id"]
        return next(r for r in _rules(conn, ctx.tenant_id, _parts(conn, ctx.tenant_id)) if r["id"] == rid)


@router.patch("/bom-rules/{rule_id}", summary="Kuralı aç / kapat")
def toggle_rule(rule_id: UUID, body: RulePatch, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        cur = conn.execute("update public.bom_rules set is_active = %s where id = %s and tenant_id = %s",
                           [body.is_active, rule_id, ctx.tenant_id])
        if cur.rowcount == 0:
            raise HTTPException(404, "Kural bulunamadı")
        return next(r for r in _rules(conn, ctx.tenant_id, _parts(conn, ctx.tenant_id)) if r["id"] == rule_id)


@router.delete("/bom-rules/{rule_id}", status_code=204, summary="Kuralı sil")
def delete_rule(rule_id: UUID, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        cur = conn.execute("delete from public.bom_rules where id = %s and tenant_id = %s", [rule_id, ctx.tenant_id])
        if cur.rowcount == 0:
            raise HTTPException(404, "Kural bulunamadı")


# ---------- eBOM ----------
def _ebom(conn, ebom_id: UUID, tenant_id: UUID) -> dict:
    b = conn.execute("select id, part_id, notes, created_at from public.eboms where id = %s and tenant_id = %s",
                     [ebom_id, tenant_id]).fetchone()
    if not b:
        raise HTTPException(404, "Mühendislik ağacı bulunamadı")
    return b


def _conversion(conn, product_id: UUID, tenant_id: UUID, parts: dict, edges: dict) -> dict:
    """Kurallar uygulanmış mBOM ve bugünkü ürün ağacıyla farkı."""
    out = convert(product_id, edges, _rules(conn, tenant_id, parts), parts)
    mbom = conn.execute("select id from public.boms where tenant_id = %s and part_id = %s",
                        [tenant_id, product_id]).fetchone()
    current = {r["part_id"]: r["qty"] for r in conn.execute(
        "select part_id, qty from public.bom_lines where bom_id = %s", [mbom["id"]]).fetchall()} if mbom else {}
    info = lambda pid: {"part_id": pid, "name": (parts.get(pid) or {}).get("name"),  # noqa: E731
                        "part_no": (parts.get(pid) or {}).get("part_no"), "unit": (parts.get(pid) or {}).get("unit")}
    lines = []
    for l in out["lines"]:
        old = current.get(l["part_id"])
        lines.append({**info(l["part_id"]), "qty": l["qty"], "ebom_qty": l["ebom_qty"], "rules": l["rules"],
                      "from_name": (parts.get(l["from_part_id"]) or {}).get("name") if l["from_part_id"] else None,
                      "current_qty": old,
                      "status": "new" if old is None else "same" if old == l["qty"] else "changed"})
    lines.sort(key=lambda r: (r["ebom_qty"] is None, (r["name"] or "").lower()))
    target = {l["part_id"] for l in out["lines"]}
    dropped = [{**info(pid), "qty": q} for pid, q in current.items() if pid not in target]
    return {"mbom_id": mbom["id"] if mbom else None, "lines": lines,
            "removed": [{**info(r["part_id"]), "qty": r["qty"], "action": r["action"], "rule": r["rule"]} for r in out["removed"]],
            # Bugünkü ürün ağacında olup dönüşümde olmayan satırlar: yazınca silinir
            "dropped": dropped,
            "in_sync": mbom is not None and not dropped and all(l["status"] == "same" for l in lines),
            "raw": out["lines"]}


def _detail(conn, b: dict, tenant_id: UUID) -> dict:
    parts, edges = _parts(conn, tenant_id), _edges(conn, tenant_id, EBOM)
    p = parts.get(b["part_id"]) or {}
    conv = _conversion(conn, b["part_id"], tenant_id, parts, edges)
    conv.pop("raw")
    return {"id": b["id"], "part_id": b["part_id"], "name": p.get("name"), "part_no": p.get("part_no"), "unit": p.get("unit"),
            "notes": b["notes"],
            "lines": [{"line_id": l["id"], "part_id": l["part_id"], "qty": l["qty"], "notes": l["notes"],
                       "name": (parts.get(l["part_id"]) or {}).get("name"), "part_no": (parts.get(l["part_id"]) or {}).get("part_no"),
                       "unit": (parts.get(l["part_id"]) or {}).get("unit"),
                       "category_code": (parts.get(l["part_id"]) or {}).get("category_code"),
                       "has_ebom": bool(edges.get(l["part_id"]))}
                      for l in edges.get(b["part_id"]) or []],
            "mbom": conv}


@router.get("/eboms", summary="Mühendislik ağaçları")
def list_eboms(ctx: TenantCtx):
    with ctx.tx() as conn:
        parts, edges = _parts(conn, ctx.tenant_id), _edges(conn, ctx.tenant_id, EBOM)
        out = []
        for b in conn.execute("select id, part_id from public.eboms where tenant_id = %s", [ctx.tenant_id]).fetchall():
            p = parts.get(b["part_id"]) or {}
            conv = _conversion(conn, b["part_id"], ctx.tenant_id, parts, edges)
            out.append({"id": b["id"], "part_id": b["part_id"], "name": p.get("name"), "part_no": p.get("part_no"),
                        "line_count": len(edges.get(b["part_id"]) or []),
                        "mbom_id": conv["mbom_id"], "in_sync": conv["in_sync"]})
        return sorted(out, key=lambda r: (r["name"] or "").lower())


@router.post("/eboms", status_code=201, summary="Bir katalog kalemi için mühendislik ağacı aç")
def create_ebom(body: BomIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        _visible_part(conn, body.part_id, ctx.tenant_id)
        b = conn.execute(
            """insert into public.eboms (tenant_id, part_id, notes, created_by) values (%s, %s, %s, %s)
               on conflict (tenant_id, part_id) do nothing returning id, part_id, notes, created_at""",
            [ctx.tenant_id, body.part_id, body.notes, ctx.user_id]).fetchone()
        if not b:
            raise HTTPException(409, "Bu kalemin mühendislik ağacı zaten var")
        return _detail(conn, b, ctx.tenant_id)


@router.post("/eboms/import", summary="Mühendislik ağaçlarını Excel'den içe aktar (ürün ağacı şablonuyla aynı sütunlar)")
def import_eboms(ctx: TenantCtx, file: Annotated[UploadFile, File(description=".xlsx")]):
    ctx.require("manager")
    return import_file(ctx, file, EBOM)


@router.get("/eboms/{ebom_id}", summary="Mühendislik ağacı ve kurallar uygulanmış mBOM önizlemesi")
def get_ebom(ebom_id: UUID, ctx: TenantCtx):
    with ctx.tx() as conn:
        return _detail(conn, _ebom(conn, ebom_id, ctx.tenant_id), ctx.tenant_id)


@router.delete("/eboms/{ebom_id}", status_code=204, summary="Mühendislik ağacını sil (ürün ağacı etkilenmez)")
def delete_ebom(ebom_id: UUID, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        _ebom(conn, ebom_id, ctx.tenant_id)
        conn.execute("delete from public.eboms where id = %s and tenant_id = %s", [ebom_id, ctx.tenant_id])


@router.post("/eboms/{ebom_id}/lines", status_code=201, summary="Mühendislik ağacına bileşen ekle")
def add_line(ebom_id: UUID, body: LineIn, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        b = _ebom(conn, ebom_id, ctx.tenant_id)
        _visible_part(conn, body.part_id, ctx.tenant_id)
        if _reaches(_edges(conn, ctx.tenant_id, EBOM), body.part_id, b["part_id"]):
            raise HTTPException(422, "Bu kalem ürünün kendisi ya da ürünü içeren bir alt montaj; ağaç döngüye girer")
        cur = conn.execute(
            """insert into public.ebom_lines (tenant_id, bom_id, part_id, qty, notes) values (%s, %s, %s, %s, %s)
               on conflict (bom_id, part_id) do nothing""",
            [ctx.tenant_id, ebom_id, body.part_id, body.qty, body.notes])
        if cur.rowcount == 0:
            raise HTTPException(409, "Bu bileşen mühendislik ağacında zaten var")
        return _detail(conn, b, ctx.tenant_id)


@router.delete("/eboms/{ebom_id}/lines/{line_id}", status_code=204, summary="Mühendislik ağacından bileşen sil")
def delete_line(ebom_id: UUID, line_id: int, ctx: TenantCtx):
    ctx.require("manager")
    with ctx.tx() as conn:
        cur = conn.execute("delete from public.ebom_lines where id = %s and bom_id = %s and tenant_id = %s",
                           [line_id, ebom_id, ctx.tenant_id])
        if cur.rowcount == 0:
            raise HTTPException(404, "Satır bulunamadı")


@router.post("/eboms/{ebom_id}/apply", summary="Kuralları uygula ve ürün ağacına (mBOM) yaz")
def apply_ebom(ebom_id: UUID, ctx: TenantCtx):
    """Ürün ağacının satırları dönüşümün sonucuyla değiştirilir; rota ve açılmış emirler etkilenmez."""
    ctx.require("manager")
    with ctx.tx() as conn:
        b = _ebom(conn, ebom_id, ctx.tenant_id)
        parts, edges = _parts(conn, ctx.tenant_id), _edges(conn, ctx.tenant_id, EBOM)
        conv = _conversion(conn, b["part_id"], ctx.tenant_id, parts, edges)
        lines = conv["raw"]
        if not lines:
            raise HTTPException(422, "Dönüşümün sonucu boş; mühendislik ağacına bileşen ekleyin ya da kuralları gözden geçirin")
        # Eklenen ve değiştirilen kalemler üretim ağaçlarında döngü yaratmasın
        graph = {k: v for k, v in _edges(conn, ctx.tenant_id).items() if k != b["part_id"]}
        for l in lines:
            if _reaches(graph, l["part_id"], b["part_id"]):
                name = (parts.get(l["part_id"]) or {}).get("name")
                raise HTTPException(422, f"{name} kalemi bu ürünü içeriyor (ya da ürünün kendisi); ürün ağacı döngüye girer")
        bom_id = conv["mbom_id"] or conn.execute(
            "insert into public.boms (tenant_id, part_id, created_by) values (%s, %s, %s) returning id",
            [ctx.tenant_id, b["part_id"], ctx.user_id]).fetchone()["id"]
        conn.execute("delete from public.bom_lines where bom_id = %s and not (part_id = any(%s))",
                     [bom_id, [l["part_id"] for l in lines]])
        for l in lines:
            conn.execute(
                """insert into public.bom_lines (tenant_id, bom_id, part_id, qty) values (%s, %s, %s, %s)
                   on conflict (bom_id, part_id) do update set qty = excluded.qty""",
                [ctx.tenant_id, bom_id, l["part_id"], l["qty"]])
        return _detail(conn, b, ctx.tenant_id)
