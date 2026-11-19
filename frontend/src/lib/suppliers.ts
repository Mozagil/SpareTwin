// Tedarikçi karşılaştırma: renkler, paylar ve "kim avantajlı" cümlesi.
// Sayılar veritabanından gelir (api/purchasing.py); burada yalnızca anlatım.
import type { ComparedPart, PartSupplierStat, SupplierStat } from "../api/types";
import { num, usd } from "./format";

const PALETTE = ["var(--tco-1)", "var(--tco-2)", "var(--tco-3)", "var(--tco-4)", "var(--tco-5)"];
export const OTHER_COLOR = "var(--unknown)";

/**
 * Renk tedarikçiyi anlatır, sırayı değil: firmanın tedarikçi listesindeki (kayıt sırası) yerine göre
 * verilir, dönem ya da süzgeç değişince değişmez. Paletten sonrası tek bir nötr renge düşer.
 */
export function supplierColors(suppliers: { supplier_id: string }[]): Map<string, string> {
  return new Map(suppliers.map((s, i) => [s.supplier_id, PALETTE[i] ?? OTHER_COLOR]));
}

export interface ShareSegment { id: string; label: string; color: string; value: number; share: number }

/** Değeri sıfırdan büyük tedarikçiler, verilen sırayla; share = toplamdaki pay (0–1). */
export function shareSegments<T extends SupplierStat>(rows: T[], value: (r: T) => number, colors: Map<string, string>): ShareSegment[] {
  const vals = rows.map((r) => ({ r, v: Math.max(Number(value(r)) || 0, 0) })).filter((x) => x.v > 0);
  const total = vals.reduce((s, x) => s + x.v, 0);
  return vals.map(({ r, v }) => ({
    id: r.supplier_id, label: r.supplier_name, color: colors.get(r.supplier_id) ?? OTHER_COLOR, value: v, share: v / total,
  }));
}

/** Söz verilen tarihte gelen teslimatların oranı (0–1); ölçülebilen teslimat yoksa null. */
export const onTimeShare = (s: Pick<SupplierStat, "on_time" | "timed">) => (s.timed > 0 ? s.on_time / s.timed : null);

export const leadDays = (v: number | string | null) => (v == null ? "–" : `${num(Math.round(Number(v)))} gün`);

const pctLess = (low: number, high: number) => `%${Math.max(Math.round(((high - low) / high) * 100), 1)}`;
const sorted = (rows: PartSupplierStat[], key: "avg_cost" | "avg_lead_days") =>
  rows.filter((r) => r[key] != null).sort((a, b) => Number(a[key]) - Number(b[key]));

/** Kalem için tek cümlelik sonuç: kim daha ucuz, kim daha hızlı. Ölçülemeyeni söylemez. */
export function verdict(part: Pick<ComparedPart, "suppliers">): string {
  const s = part.suppliers;
  if (s.length < 2) return "Tek tedarikçiden alınıyor; karşılaştırma için ikinci bir kaynak gerekir.";
  const cheap = s.find((r) => r.cheapest), fast = s.find((r) => r.fastest);
  const byCost = sorted(s, "avg_cost"), byLead = sorted(s, "avg_lead_days");
  const price = cheap && byCost[1] ? pctLess(Number(byCost[0]!.avg_cost), Number(byCost[1].avg_cost)) : "";
  const days = fast && byLead[1] ? Math.max(Math.round(Number(byLead[1].avg_lead_days) - Number(byLead[0]!.avg_lead_days)), 1) : 0;
  if (cheap && fast && cheap.supplier_id === fast.supplier_id)
    return `${cheap.supplier_name} hem ${price} daha ucuz hem ortalama ${num(days)} gün daha hızlı.`;
  if (cheap && fast) return `${cheap.supplier_name} ${price} daha ucuz; ${fast.supplier_name} ortalama ${num(days)} gün daha hızlı teslim ediyor.`;
  if (cheap) return `${cheap.supplier_name} ${price} daha ucuz. Teslim süresini karşılaştırmak için yeterli teslimat yok.`;
  if (fast) return `${fast.supplier_name} ortalama ${num(days)} gün daha hızlı teslim ediyor; fiyat farkı yok.`;
  return "Fiyat ve teslim süresinde belirgin fark yok.";
}

/** Sipariş anında kalemin altında: "Volvo $85,21 · 7 gün (5 alım)" */
export function lastBuys(part: Pick<ComparedPart, "suppliers"> | undefined): string {
  if (!part) return "";
  return part.suppliers
    .map((s) => `${s.supplier_name} ${usd(s.avg_cost == null ? null : Number(s.avg_cost))}${s.avg_lead_days != null ? ` · ${leadDays(s.avg_lead_days)}` : ""} (${num(s.order_count)} alım)`)
    .join("  |  ");
}
