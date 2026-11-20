"""eBOM → mBOM dönüşümü: firmanın kurallarını mühendislik ağacına uygular.

Saf hesap; veritabanına dokunmaz (api/ebom.py çağırır). Sıra sabittir ve
kuralların tanımlanma sırasından bağımsızdır:

  1. düzleştir (flatten)   alt montaj yerine bileşenleri
  2. çıkar (exclude)       mBOM'a girmeyen kalemler
  3. değiştir (substitute) A yerine B, oranla
  4. sarf ekle (add)       ürün başına ya da eşleşen birim başına
  5. fire payı (scrap)     miktarı yüzdeyle artır; en özel kural geçerli
                           (tek kalem > parça tipi > tümü)

Sarf ekleme 3. adımın sonundaki ağaca bakar: eklenen sarf başka bir sarfı
tetiklemez. Fire payı eklenen ve değiştirilen kalemlere de uygulanır.
"""

from decimal import Decimal
from uuid import UUID

ACTIONS = ("flatten", "exclude", "substitute", "add", "scrap")
Q = Decimal("0.0001")


def matches(rule: dict, part_id: UUID, parts: dict) -> bool:
    if rule["match_part_id"] is not None:
        return rule["match_part_id"] == part_id
    if rule["match_category"] is not None:
        return (parts.get(part_id) or {}).get("category_code") == rule["match_category"]
    return True


def _specificity(rule: dict) -> int:
    return 2 if rule["match_part_id"] is not None else 1 if rule["match_category"] is not None else 0


def convert(product_id: UUID, edges: dict[UUID, list[dict]], rules: list[dict], parts: dict[UUID, dict]) -> dict:
    """1 birim ürün için mBOM satırları.

    edges: ürün → eBOM satırları ({part_id, qty}); rules: bom_rules satırları (+ "label");
    parts: kalem → {category_code}. Dönen: {"lines": [{part_id, qty, ebom_qty, from_part_id, rules}],
    "removed": [{part_id, qty, action, rule}]}. ebom_qty boşsa satır kuralla eklenmiştir.
    """
    by = {a: [r for r in rules if r["action"] == a and r["is_active"]] for a in ACTIONS}
    first = lambda action, pid: next((r for r in by[action] if matches(r, pid, parts)), None)  # noqa: E731
    lines: list[dict] = []
    removed: list[dict] = []

    def expand(pid: UUID, mult: Decimal, path: frozenset, via: list[str]) -> None:
        for l in edges.get(pid) or []:
            c, q = l["part_id"], l["qty"] * mult
            rule = first("flatten", c)
            if rule and edges.get(c) and c not in path:
                removed.append({"part_id": c, "qty": q, "action": "flatten", "rule": rule["label"]})
                expand(c, q, path | {c}, [*via, rule["label"]])
            else:
                lines.append({"part_id": c, "qty": q, "ebom_qty": q, "from_part_id": None, "rules": list(via)})

    expand(product_id, Decimal(1), frozenset({product_id}), [])

    merged: dict[UUID, dict] = {}

    def put(line: dict) -> None:
        cur = merged.get(line["part_id"])
        if cur is None:
            merged[line["part_id"]] = line
            return
        cur["qty"] += line["qty"]
        if line["ebom_qty"] is not None:
            cur["ebom_qty"] = (cur["ebom_qty"] or Decimal(0)) + line["ebom_qty"]
        cur["from_part_id"] = cur["from_part_id"] or line["from_part_id"]
        cur["rules"] += [r for r in line["rules"] if r not in cur["rules"]]

    for l in lines:
        rule = first("exclude", l["part_id"])
        if rule:
            removed.append({"part_id": l["part_id"], "qty": l["qty"], "action": "exclude", "rule": rule["label"]})
            continue
        rule = first("substitute", l["part_id"])
        if rule:
            l = {**l, "from_part_id": l["part_id"], "part_id": rule["target_part_id"],
                 "qty": l["qty"] * rule["qty"], "rules": [*l["rules"], rule["label"]]}
        put(l)

    base = [(pid, l["qty"]) for pid, l in merged.items()]
    for rule in by["add"]:
        hit = [q for pid, q in base if matches(rule, pid, parts)]
        if not hit:
            continue
        times = Decimal(1) if rule["per"] == "product" else sum(hit, Decimal(0))
        put({"part_id": rule["target_part_id"], "qty": rule["qty"] * times, "ebom_qty": None,
             "from_part_id": None, "rules": [rule["label"]]})

    for l in merged.values():
        cands = [r for r in by["scrap"] if matches(r, l["part_id"], parts)]
        if cands:
            rule = max(cands, key=_specificity)
            l["qty"] *= 1 + rule["scrap_pct"] / Decimal(100)
            l["rules"].append(rule["label"])
        l["qty"] = l["qty"].quantize(Q)
    return {"lines": list(merged.values()), "removed": removed}
