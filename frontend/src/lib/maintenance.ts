// Bakım: etiketler ve cümleler. Kurallar veritabanında (0015); burada yalnızca anlatım.
import type { Band, DueState, MaintenanceDue, ReasonCode, WoKind, WoStatus } from "../api/types";
import { date, num } from "./format";

export const WO_STATUS_LABEL: Record<WoStatus, string> = {
  open: "Açık", in_progress: "Sürüyor", done: "Tamamlandı", cancelled: "İptal",
};
export const WO_STATUS_BAND: Record<WoStatus, Band> = {
  open: "watch", in_progress: "watch", done: "ok", cancelled: "unknown",
};
export const WO_KIND_LABEL: Record<WoKind, string> = { planned: "Planlı bakım", breakdown: "Arıza" };

export const DUE_STATE_LABEL: Record<DueState, string> = { overdue: "Gecikti", due_soon: "Yaklaşıyor", ok: "Zamanında" };
export const DUE_STATE_BAND: Record<DueState, Band> = { overdue: "critical", due_soon: "watch", ok: "ok" };

export const REASON_LABEL: Record<ReasonCode, string> = {
  hydraulic: "Hidrolik", electrical: "Elektrik", engine: "Motor", tire: "Lastik", transmission: "Şanzıman / aktarma",
  structural: "Yapısal / kaynak", operator: "Operatör hatası", other: "Diğer",
};
export const REASONS = Object.keys(REASON_LABEL) as ReasonCode[];

/** 330 → "5 sa 30 dk"; 45 → "45 dk"; 0 / null → "–" */
export const downtime = (minutes: number | null | undefined) => {
  if (!minutes) return "–";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h === 0) return `${m} dk`;
  return m ? `${num(h)} sa ${m} dk` : `${num(h)} sa`;
};

/** Planın periyodu: "500 saat", "180 gün", "500 saat / 180 gün" */
export const intervalLabel = (p: { interval_hours: number | null; interval_days: number | null }) =>
  [p.interval_hours != null ? `${num(Number(p.interval_hours))} saat` : null, p.interval_days != null ? `${p.interval_days} gün` : null]
    .filter(Boolean).join(" / ");

/** Kalan: "20 saat kaldı (yaklaşık 3 gün)", "5 gün kaldı", "40 saat geçti" */
export function dueLeft(d: Pick<MaintenanceDue, "hours_left" | "days_left" | "eta_at" | "next_due_at" | "hours_per_day">): string {
  const parts: string[] = [];
  if (d.hours_left != null) {
    const h = Number(d.hours_left);
    parts.push(h < 0 ? `${num(-h)} saat geçti` : `${num(h)} saat kaldı`);
  }
  if (d.days_left != null) {
    const n = Number(d.days_left);
    parts.push(n < 0 ? `${-n} gün geçti` : n === 0 ? "bugün" : `${n} gün kaldı`);
  }
  let s = parts.join(", ");
  if (d.hours_left != null && Number(d.hours_left) >= 0 && d.hours_per_day && d.eta_at && d.eta_at !== d.next_due_at) {
    s += ` (yaklaşık ${date(d.eta_at)})`;
  }
  return s || "–";
}

/** Dashboard ve bildirim cümlesi: "Son bakım 12.000 saatte; sıradaki 12.500 saatte, 20 saat kaldı." */
export function dueWhy(d: MaintenanceDue): string {
  const last = d.last_done_hours != null ? `Son bakım ${num(Number(d.last_done_hours))} saatte`
    : d.last_done_at ? `Son bakım ${date(d.last_done_at)}` : "Hiç yapılmadı";
  const next = [
    d.next_due_hours != null ? `sıradaki ${num(Number(d.next_due_hours))} saatte` : null,
    d.next_due_at != null ? `tarih ${date(d.next_due_at)}` : null,
  ].filter(Boolean).join(", ");
  return `${last}; ${next}, ${dueLeft(d)}.`;
}

/** Periyodun ne kadarı doldu (0–1); ilerleme çubuğu için. */
export function dueProgress(d: MaintenanceDue): number {
  const r: number[] = [];
  if (d.interval_hours && d.hours_left != null) r.push(1 - Number(d.hours_left) / Number(d.interval_hours));
  if (d.interval_days && d.days_left != null) r.push(1 - Number(d.days_left) / d.interval_days);
  return Math.min(1, Math.max(0, ...r, 0));
}
