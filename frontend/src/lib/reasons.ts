// Sökme sebebi raporu: anlatım. Sayılar API'den gelir (GET /reports/removal-reasons).
import type { RemovalReasons } from "../api/types";
import { num, reasonLabel } from "./format";

/** "Aşınma (ömür sonu) 3 · Kesik / yırtık 2": en sık sebep önce (API sırası) */
export const reasonMix = (reasons: Record<string, number>) =>
  Object.entries(reasons).map(([code, n]) => `${reasonLabel(code)} ${num(n)}`).join(" · ");

/** Ömrünü doldurmadan (aşınma dışı bir sebeple) sökülenlerin payı, 0–1; sökme yoksa null. */
export function prematureShare(rep: Pick<RemovalReasons, "total" | "reasons">): number | null {
  if (rep.total <= 0) return null;
  const worn = rep.reasons.find((r) => r.reason === "worn_out")?.count ?? 0;
  return (rep.total - worn) / rep.total;
}

/** Çubuk genişliği: en sık sebebe göre, 0–100. Sıfırdan büyük her sebep görünür kalsın diye alt sınır var. */
export const barWidth = (count: number, max: number) => (max <= 0 ? 0 : Math.max((count / max) * 100, 2));
