import type { PoStatus, PurchaseNeed, PurchaseOrderLine } from "../api/types";
import { CATEGORY_LABEL, num } from "./format";

export const PO_STATUS_LABEL: Record<PoStatus, string> = {
  draft: "Talep", ordered: "Sipariş verildi", partial: "Kısmen teslim", received: "Teslim alındı", cancelled: "İptal",
};

/** Durum rengi: açık siparişler nötr, geciken izlemede, kapananlar yeşil / gri. */
export const PO_STATUS_BAND: Record<PoStatus, "ok" | "watch" | "unknown" | "empty"> = {
  draft: "unknown", ordered: "watch", partial: "watch", received: "ok", cancelled: "empty",
};

/** Satır tutarı; fiyat yoksa null. */
export const lineTotal = (l: Pick<PurchaseOrderLine, "qty" | "unit_cost">) =>
  l.unit_cost == null ? null : Number(l.qty) * Number(l.unit_cost);

/** Teslim alınan oran (0–1). */
export const orderProgress = (lines: Pick<PurchaseOrderLine, "qty" | "received_qty">[]) => {
  const total = lines.reduce((s, l) => s + Number(l.qty), 0);
  return total ? lines.reduce((s, l) => s + Number(l.received_qty), 0) / total : 0;
};

const lower = (code: string) => (CATEGORY_LABEL[code] ?? code).toLocaleLowerCase("tr");

/** İhtiyacın nedeni tek cümlede: "LD-07, LD-09 için 2 lastik yaklaşıyor, stokta 1 var, siparişte 0." */
export function needWhy(n: PurchaseNeed): string {
  const assets = [...new Set((n.items ?? []).map((i) => i.asset_code).filter(Boolean))];
  const parts: string[] = [];
  if (n.upcoming > 0) {
    const who = assets.length > 3 ? `${assets.slice(0, 3).join(", ")} ve diğerleri` : assets.join(", ");
    parts.push(`${who} için ${n.upcoming} ${lower(n.category_code)} yaklaşıyor`);
  } else {
    parts.push(`Kritik seviye ${num(n.min_stock)} ${n.unit}`);
  }
  parts.push(Number(n.in_stock) > 0 ? `stokta ${num(Number(n.in_stock))} var` : "stokta yok");
  if (Number(n.on_order) > 0) parts.push(`siparişte ${num(Number(n.on_order))}`);
  if (Number(n.requested) > 0) parts.push(`talepte ${num(Number(n.requested))}`);
  return parts.join(", ") + ".";
}

/** Yaklaşan parçanın kısa etiketi: "LD-07 A2-L · %13" ya da "LD-09 A1-R · 420 saat". */
export const needItemLabel = (i: NonNullable<PurchaseNeed["items"]>[number]) =>
  `${i.asset_code} ${i.position}` +
  (i.band === "critical" && i.condition_pct != null ? ` · %${num(Number(i.condition_pct))}`
    : i.hours_left != null ? ` · ${num(Number(i.hours_left))} saat` : "");
