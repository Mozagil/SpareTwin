// Makine devri: kod biçimi ve durum anlatımı. Kurallar veritabanında (0024).
import type { TransferRow, TransferStatus } from "../api/types";

export const TRANSFER_STATUS: Record<TransferStatus, string> = {
  pending: "Bekliyor",
  accepted: "Devredildi",
  cancelled: "İptal edildi",
  expired: "Süresi doldu",
};

/** Durum çipi: alıcı tarafta "Devredildi" yerine "Devralındı" yazar. */
export const transferLabel = (t: Pick<TransferRow, "status" | "direction">) =>
  t.status === "accepted" && t.direction === "in" ? "Devralındı" : TRANSFER_STATUS[t.status];

export const transferTone = (s: TransferStatus) => (s === "accepted" ? "t-ok" : s === "pending" ? "t-watch" : "chip-plain");

/**
 * Elle ya da telefondan yazılan kodu sunucunun beklediği biçime getirir:
 * "dv 3fa9 c1b2e4" → "DV-3FA9C1B2E4". Önek yazılmadıysa eklenir.
 */
export function normalizeTransferCode(raw: string): string {
  const s = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (!s) return "";
  return `DV-${s.startsWith("DV") ? s.slice(2) : s}`;
}

/** Kodun kalan süresi: "12 gün", son gün "bugün"; süresi dolduysa null. */
export function daysLeft(expiresAt: string, now: Date = new Date()): string | null {
  const ms = new Date(expiresAt).getTime() - now.getTime();
  if (ms <= 0) return null;
  const days = Math.ceil(ms / 86_400_000);
  return days <= 1 ? "bugün" : `${days} gün`;
}
