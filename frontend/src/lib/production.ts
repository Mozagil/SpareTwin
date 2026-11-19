// Üretim yardımcıları: ürün ağacını tablo satırlarına açar; emir durumu ve süre gösterimi.
import type { ProdStatus, ProductLine, ScrapReason } from "../api/types";

export const PROD_STATUS_LABEL: Record<ProdStatus, string> = {
  open: "Açık", in_progress: "Sürüyor", done: "Tamamlandı", cancelled: "İptal",
};
export const PROD_STATUS_BAND: Record<ProdStatus, "ok" | "watch" | "unknown" | "empty"> = {
  open: "unknown", in_progress: "watch", done: "ok", cancelled: "empty",
};

/** Dakikayı okunur süreye çevirir: 135 → "2 sa 15 dk", 40 → "40 dk", 0.4 → "1 dk'dan az". */
export function duration(minutes: number | string | null | undefined): string {
  if (minutes == null) return "–";
  const m = Math.round(Number(minutes));
  if (m === 0) return Number(minutes) > 0 ? "1 dk'dan az" : "0 dk";
  const h = Math.floor(m / 60);
  return h === 0 ? `${m} dk` : m % 60 === 0 ? `${h} sa` : `${h} sa ${m % 60} dk`;
}

/** Plana göre sapma yüzdesi (+ gecikme, − erken); plan yoksa null. */
export function deviation(planned: number | string | null | undefined, actual: number | string): number | null {
  const p = Number(planned);
  return planned == null || !(p > 0) ? null : Math.round(((Number(actual) - p) / p) * 100);
}

export const SCRAP_REASON_LABEL: Record<ScrapReason, string> = {
  material: "Malzeme hatası", workmanship: "İşçilik hatası", machine: "Makine / kalıp arızası", setup: "Ayar / deneme üretimi",
  dimension: "Ölçü dışı", damage: "Taşıma / depolama hasarı", other: "Diğer",
};
export const SCRAP_REASONS = Object.keys(SCRAP_REASON_LABEL) as ScrapReason[];

/** Malzeme firesi: kullanılan − planlanan (eksi = tasarruf) ve plana oranı (%). */
export function waste(planned: number | string, actual: number | string): { diff: number; pct: number } {
  const p = Number(planned);
  const diff = Math.round((Number(actual) - p) * 10000) / 10000;
  return { diff, pct: p > 0 ? Math.round((diff / p) * 100) : 0 };
}

/** Maliyet farkı: gerçekleşen − planlanan, kuruşa yuvarlı (eksi = plandan ucuz). */
export function costDiff(planned: number | string, actual: number | string): number {
  return Math.round((Number(actual) - Number(planned)) * 100) / 100;
}

export interface FlatLine extends ProductLine {
  depth: number;
  /** Kökten bu satıra yol; açma/kapama ve React anahtarı */
  path: string;
}

/** Ağacı derinlik sırasıyla düz listeye çevirir; kapalı alt montajların çocukları atlanır. */
export function flatten(lines: ProductLine[], closed: ReadonlySet<string> = new Set(), depth = 0, prefix = ""): FlatLine[] {
  return lines.flatMap((l) => {
    const path = `${prefix}/${l.part_id}`;
    const row = { ...l, depth, path };
    return closed.has(path) ? [row] : [row, ...flatten(l.children, closed, depth + 1, path)];
  });
}

/** Satın alınacak / stoktan çekilecek yapraklar: aynı kalem ağacın farklı dallarında geçiyorsa miktarı toplanır. */
export function leafTotals(lines: ProductLine[]): { part_id: string; name: string | null; unit: string | null; qty: number; in_stock: number }[] {
  const out = new Map<string, { part_id: string; name: string | null; unit: string | null; qty: number; in_stock: number }>();
  const walk = (ls: ProductLine[]) => ls.forEach((l) => {
    if (l.children.length > 0) return walk(l.children);
    const cur = out.get(l.part_id);
    if (cur) cur.qty += Number(l.total_qty);
    else out.set(l.part_id, { part_id: l.part_id, name: l.name, unit: l.unit, qty: Number(l.total_qty), in_stock: Number(l.in_stock) });
  });
  walk(lines);
  return [...out.values()];
}
