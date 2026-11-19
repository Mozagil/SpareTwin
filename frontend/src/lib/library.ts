// Firma kütüphanesi (parça tipleri, pozisyon şablonları): arayüz doğrulaması ve
// şema düzenleyicinin hesapları. Aynı kurallar API'de de uygulanır (api/library.py).
import type { Layout, ProfileItem, Template, TemplatePosition } from "../api/types";

const TR: Record<string, string> = { ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u" };
const ascii = (s: string) => s.toLocaleLowerCase("tr").replace(/[çğıöşü]/g, (c) => TR[c]!);

/** Addan kalıcı kod: "Şanzıman / dişli" → "sanziman_disli". Harfle başlar, en çok 40 karakter. */
export function slugify(name: string): string {
  const s = ascii(name).replace(/[^a-z0-9]+/g, "_").replace(/^[_0-9]+|_+$/g, "").slice(0, 40).replace(/_+$/, "");
  return s.length >= 2 ? s : "";
}
export const SLUG_RE = /^[a-z][a-z0-9_]{1,39}$/;

/** Pozisyon kodu yazılırken: büyük harf, yalnızca harf/rakam/tire/alt çizgi. */
export const positionCode = (text: string) =>
  ascii(text).toUpperCase().replace(/\s+/g, "-").replace(/[^A-Z0-9_-]/g, "").slice(0, 24);
export const POSITION_RE = /^[A-Z0-9][A-Z0-9_-]{0,23}$/;

// ---------- Ölçüm profili ----------
export interface MetricDraft {
  /** Kayıtlı ölçümün anahtarı; geçmiş ölçümler buna bağlı olduğu için değişmez. Yeni satırda boş. */
  metric: string;
  label: string;
  unit: string;
  min: string;
  max: string;
  required: boolean;
}
export const emptyMetric = (): MetricDraft => ({ metric: "", label: "", unit: "", min: "", max: "", required: false });

export const toMetricDrafts = (profile: ProfileItem[]): MetricDraft[] =>
  profile.map((m) => ({
    metric: m.metric, label: m.label, unit: m.unit ?? "", required: !!m.required,
    min: m.min == null ? "" : String(m.min), max: m.max == null ? "" : String(m.max),
  }));

const numOrNull = (s: string) => {
  const n = Number(s.trim().replace(",", "."));
  return s.trim() === "" ? null : Number.isFinite(n) ? n : NaN;
};

/** Taslak satırları API gövdesine çevirir; hata varsa `errors` dolu, `profile` null. */
export function buildProfile(rows: MetricDraft[]): { errors: string[]; profile: ProfileItem[] | null } {
  const errors: string[] = [];
  const seen = new Set<string>();
  const profile: ProfileItem[] = [];
  rows.forEach((r, i) => {
    const n = i + 1;
    const label = r.label.trim();
    if (!label) return void errors.push(`${n}. ölçüm: ad girin`);
    const metric = r.metric || slugify(`${label} ${r.unit}`);
    if (!SLUG_RE.test(metric)) return void errors.push(`${n}. ölçüm: ad harfle başlamalı`);
    if (seen.has(metric)) return void errors.push(`${n}. ölçüm: “${label}” iki kez var`);
    seen.add(metric);
    const min = numOrNull(r.min), max = numOrNull(r.max);
    if (Number.isNaN(min) || Number.isNaN(max)) return void errors.push(`${n}. ölçüm: sınırlar sayı olmalı`);
    if (min != null && max != null && min >= max) return void errors.push(`${n}. ölçüm: alt sınır üst sınırdan küçük olmalı`);
    profile.push({
      metric, label, unit: r.unit.trim(), required: r.required,
      ...(min != null ? { min } : {}), ...(max != null ? { max } : {}),
    });
  });
  return { errors, profile: errors.length ? null : profile };
}

// ---------- Pozisyon şablonu ----------
export interface PositionDraft {
  /** Satırın arayüzdeki kimliği; kod düzenlenirken satır yerinden oynamasın diye */
  key: number;
  code: string;
  label: string;
  category_code: string;
  axle: string;
  x: number | null;
  y: number | null;
}
export interface TemplateDraft {
  id?: string;
  name: string;
  layout: Layout;
  positions: PositionDraft[];
}

let seq = 0;
const nextKey = () => ++seq;

export const emptyTemplate = (): TemplateDraft => ({ name: "", layout: "generic", positions: [] });

/** Var olan şablondan taslak. `copy` ise yeni şablon olarak kaydedilir (ortak şablonu uyarlamak için). */
export function toTemplateDraft(t: Template, copy = false): TemplateDraft {
  return {
    ...(copy ? {} : { id: t.id }),
    name: copy ? `${t.name} (kopya)`.slice(0, 80) : t.name,
    layout: t.layout,
    positions: t.positions.map((p) => ({
      key: nextKey(), code: p.code, label: p.label, category_code: p.category_code,
      axle: p.axle == null ? "" : String(p.axle),
      x: p.x == null ? null : Number(p.x), y: p.y == null ? null : Number(p.y),
    })),
  };
}

/** Kullanılmayan ilk kod: P1, P2, … */
export function nextCode(positions: { code: string }[], prefix = "P"): string {
  const used = new Set(positions.map((p) => p.code));
  for (let i = 1; ; i++) if (!used.has(`${prefix}${i}`)) return `${prefix}${i}`;
}

export function newPosition(positions: PositionDraft[], category_code: string): PositionDraft {
  const code = nextCode(positions);
  // Yeni yuvalar üst üste binmesin: şemanın ortasından sağa doğru dizilir
  const n = positions.filter((p) => p.x != null).length;
  return { key: nextKey(), code, label: "", category_code, axle: "", x: 30 + (n % 5) * 10, y: 50 };
}

/** Her lastik yuvasına jant yuvası (KOD-J) ekler; var olanlara dokunmaz. Jant şemada çizilmez. */
export function withRimSlots(positions: PositionDraft[]): PositionDraft[] {
  const codes = new Set(positions.map((p) => p.code));
  const rims = positions
    .filter((p) => p.category_code === "tire" && p.code && !codes.has(`${p.code}-J`) && `${p.code}-J`.length <= 24)
    .map((p) => ({ key: nextKey(), code: `${p.code}-J`, label: `${p.label || p.code} jantı`.slice(0, 60), category_code: "rim", axle: p.axle, x: null, y: null }));
  return [...positions, ...rims];
}

// Şema koordinatları: MachineSchematic ile aynı dönüşüm (viewBox 640×360, konum 0–100)
const clamp = (v: number) => Math.min(100, Math.max(0, Math.round(v)));
export const svgToPct = (sx: number, sy: number) => ({ x: clamp((sx - 40) / 5.6), y: clamp((sy - 20) / 3.2) });
export const nudge = (p: { x: number | null; y: number | null }, dx: number, dy: number) =>
  p.x == null || p.y == null ? p : { ...p, x: clamp(p.x + dx), y: clamp(p.y + dy) };

/** Taslağı API gövdesine çevirir; hata varsa `errors` dolu, `body` null. */
export function buildTemplate(d: TemplateDraft): {
  errors: string[];
  body: { name: string; layout: Layout; positions: TemplatePosition[] } | null;
} {
  const errors: string[] = [];
  if (d.name.trim().length < 2) errors.push("Şablona bir ad verin");
  if (d.positions.length === 0) errors.push("En az bir yuva ekleyin");
  const seen = new Set<string>();
  const positions: TemplatePosition[] = [];
  for (const p of d.positions) {
    const name = p.code || "(kodsuz yuva)";
    if (!POSITION_RE.test(p.code)) errors.push(`${name}: kod büyük harf, rakam ve tire içerebilir`);
    else if (seen.has(p.code)) errors.push(`${p.code}: bu kod iki kez var`);
    seen.add(p.code);
    if (!p.label.trim()) errors.push(`${name}: ad girin`);
    const axle = p.axle.trim() === "" ? null : Number(p.axle);
    if (axle != null && !(Number.isInteger(axle) && axle >= 1 && axle <= 12)) errors.push(`${name}: aks 1 ile 12 arasında olmalı`);
    positions.push({ code: p.code, label: p.label.trim(), category_code: p.category_code, axle, x: p.x, y: p.y });
  }
  return { errors, body: errors.length ? null : { name: d.name.trim(), layout: d.layout, positions } };
}
