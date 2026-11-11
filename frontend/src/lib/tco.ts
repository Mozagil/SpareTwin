// Maliyet raporu (TCO): kalem etiketleri ve dağılım. Hesap veritabanında (0016); burada yalnızca anlatım.
import type { TcoCosts, TcoRow } from "../api/types";

export type TcoKey = "parts_cost" | "consumables_cost" | "labor_cost" | "external_cost" | "downtime_cost";

/** Kalemlerin sırası ve rengi sabittir: renk kalemi anlatır, sıralamayı değil. */
export const TCO_ITEMS: { key: TcoKey; label: string; hint: string; color: string }[] = [
  { key: "parts_cost", label: "Parça", color: "var(--tco-1)", hint: "Seri numaralı parçaların alış maliyeti (ilk takıldığı makineye) + tamir / yenileme" },
  { key: "consumables_cost", label: "Sarf", color: "var(--tco-2)", hint: "Stoktan makineye çıkan filtre, yağ, keçe; ortalama maliyetle" },
  { key: "labor_cost", label: "İşçilik", color: "var(--tco-3)", hint: "Tamamlanan iş emirlerinin işçilik maliyeti" },
  { key: "external_cost", label: "Dış servis", color: "var(--tco-4)", hint: "Tamamlanan iş emirlerinin dış servis ve nakliye maliyeti" },
  { key: "downtime_cost", label: "Duruş", color: "var(--tco-5)", hint: "Arıza duruş süresi × firmanın duruş saat maliyeti" },
];

export interface TcoSegment { key: TcoKey; label: string; color: string; value: number; share: number }

/** Sıfırdan büyük kalemler, sabit sırayla; share = kalemin toplamdaki payı (0–1). */
export function tcoSegments(c: TcoCosts): TcoSegment[] {
  const total = TCO_ITEMS.reduce((s, i) => s + Math.max(Number(c[i.key]) || 0, 0), 0);
  if (total <= 0) return [];
  return TCO_ITEMS
    .map((i) => ({ key: i.key, label: i.label, color: i.color, value: Math.max(Number(c[i.key]) || 0, 0) }))
    .filter((s) => s.value > 0)
    .map((s) => ({ ...s, share: s.value / total }));
}

/** %62, %0,4; yuvarlanınca sıfır görünen küçük paylar "<%1" */
export const sharePct = (share: number) => (share > 0 && share < 0.01 ? "<%1" : `%${Math.round(share * 100)}`);

/**
 * Saat kaydı dönem başından belirgin biçimde sonra başlıyorsa (7 günden fazla) saat başı maliyet
 * olduğundan yüksek görünür: maliyet tüm dönemden, saat yalnızca kaydın olduğu kısımdan gelir.
 */
export function hoursPartial(row: Pick<TcoRow, "hours_from">, periodFrom: string): boolean {
  if (!row.hours_from) return false;
  return new Date(row.hours_from).getTime() - new Date(periodFrom).getTime() > 7 * 86_400_000;
}

/** Oran alanı: boş = makineye özel oran yok (null); geçersiz ya da sınır dışı = undefined. */
export function rateFromInput(text: string): number | null | undefined {
  const t = text.trim().replace(",", ".");
  if (!t) return null;
  const v = Number(t);
  return Number.isFinite(v) && v >= 0 && v <= 100_000 ? v : undefined;
}

export const TCO_PERIODS: { months: number; label: string }[] = [
  { months: 3, label: "Son 3 ay" }, { months: 6, label: "Son 6 ay" }, { months: 12, label: "Son 12 ay" }, { months: 24, label: "Son 24 ay" },
];
