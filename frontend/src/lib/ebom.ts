// eBOM → mBOM: kural formu ve durum anlatımı. Dönüşümün kendisi sunucuda (backend/sparetwin/ebom.py).
import type { BomRuleIn, EbomRow, RuleAction } from "../api/types";

export const RULE_ACTIONS: { key: RuleAction; label: string; hint: string }[] = [
  { key: "scrap", label: "Fire payı", hint: "Eşleşen kalemin miktarı yüzdeyle artar (sac +%5, yağ +%3)." },
  { key: "add", label: "Sarf ekle", hint: "Tasarımda olmayan kalem eklenir: ürün başına ya da eşleşen her birim için." },
  { key: "substitute", label: "Değiştir", hint: "Tasarımdaki kalem yerine üretimde başka bir kalem kullanılır." },
  { key: "exclude", label: "Çıkar", hint: "Eşleşen kalem üretim ağacına girmez (referans, doküman)." },
  { key: "flatten", label: "Düzleştir", hint: "Alt montaj ayrı üretilmez; bileşenleri üst ürüne açılır." },
];

export type MatchKind = "all" | "category" | "part";

export interface RuleForm {
  action: RuleAction;
  match: MatchKind;
  matchPart: string;
  matchCategory: string;
  target: string;
  qty: string;
  per: "product" | "match";
  pct: string;
}

export const EMPTY_RULE: RuleForm = { action: "scrap", match: "category", matchPart: "", matchCategory: "", target: "", qty: "1", per: "product", pct: "5" };

/** Kural tipinin kabul ettiği eşleşmeler: değiştirme tek kalemle, çıkar / düzleştir "tümü" olmadan. */
export function matchKinds(action: RuleAction): MatchKind[] {
  if (action === "substitute") return ["part"];
  if (action === "exclude" || action === "flatten") return ["category", "part"];
  return ["category", "part", "all"];
}

const n = (v: string) => Number(v.replace(",", "."));

/** Formu API gövdesine çevirir; eksik ya da geçersizse nedenini döner. */
export function buildRule(f: RuleForm): { body: BomRuleIn } | { error: string } {
  const match = matchKinds(f.action).includes(f.match) ? f.match : matchKinds(f.action)[0]!;
  if (match === "part" && !f.matchPart) return { error: "Eşleşecek kalemi seçin" };
  if (match === "category" && !f.matchCategory) return { error: "Eşleşecek parça tipini seçin" };
  const body: BomRuleIn = {
    action: f.action,
    match_part_id: match === "part" ? f.matchPart : null,
    match_category: match === "category" ? f.matchCategory : null,
  };
  if (f.action === "scrap") {
    const pct = n(f.pct);
    if (!(pct > 0 && pct <= 100)) return { error: "Fire payı 0 ile 100 arasında bir yüzde olmalı" };
    body.scrap_pct = pct;
  }
  if (f.action === "substitute" || f.action === "add") {
    const qty = n(f.qty);
    if (!f.target) return { error: f.action === "add" ? "Eklenecek kalemi seçin" : "Yerine geçecek kalemi seçin" };
    if (!(qty > 0)) return { error: "Miktar sıfırdan büyük olmalı" };
    if (f.action === "substitute" && f.target === f.matchPart) return { error: "Kalem kendisiyle değiştirilemez" };
    body.target_part_id = f.target;
    body.qty = qty;
  }
  if (f.action === "add") {
    if (f.per === "match" && match === "all") return { error: "Birim başına ekleme için kalem ya da parça tipi seçin" };
    body.per = f.per;
  }
  return { body };
}

/** Listede eBOM'un üretim ağacıyla durumu. */
export function ebomState(e: Pick<EbomRow, "mbom_id" | "in_sync" | "line_count">): { label: string; tone: string } {
  if (e.line_count === 0) return { label: "boş", tone: "chip-plain" };
  if (!e.mbom_id) return { label: "dönüştürülmedi", tone: "t-watch" };
  return e.in_sync ? { label: "üretim ağacı güncel", tone: "t-ok" } : { label: "fark var", tone: "t-watch" };
}
