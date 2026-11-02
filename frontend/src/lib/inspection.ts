import type { ProfileItem, SheetItem } from "../api/types";
import { num1 } from "./format";

/** Girilen değer makul aralıkta mı? Uyarı metni ya da null. */
export function rangeWarning(p: ProfileItem, raw: string, previous?: number): string | null {
  if (raw.trim() === "") return null;
  const v = Number(raw.replace(",", "."));
  if (!Number.isFinite(v)) return "Sayı girin";
  if (p.min != null && v < p.min) return `En az ${num1(p.min)} ${p.unit ?? ""} olabilir`.trim();
  if (p.max != null && v > p.max) return `En fazla ${num1(p.max)} ${p.unit ?? ""} olabilir`.trim();
  // Diş derinliği zamanla azalır; önceki ölçümden belirgin fazlaysa yanlış ölçüm olabilir
  if (p.metric === "tread_depth_mm" && previous != null && v > previous + 2)
    return `Önceki ölçüm ${num1(previous)} mm idi; diş derinliği artmaz. Tekrar ölçün.`;
  return null;
}

export const parseNum = (raw: string) => Number(raw.replace(",", "."));

/** Sıradaki yapılacak pozisyon: önce zorunlu ve eksik olanlar. */
export function nextIncomplete(items: SheetItem[], after?: string): SheetItem | undefined {
  const todo = items.filter((i) => i.required && !i.complete);
  if (!after) return todo[0];
  const idx = items.findIndex((i) => i.position === after);
  return todo.find((i) => items.indexOf(i) > idx) ?? todo[0];
}

export function itemState(i: SheetItem): "done" | "partial" | "todo" | "optional" {
  if (i.complete) return "done";
  if (i.started) return "partial";
  return i.required ? "todo" : "optional";
}
