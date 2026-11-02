import type { Band, PartStatus } from "../api/types";

const nf0 = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1 });
const money = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dateFmt = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export const num = (v: number | null | undefined) => (v == null ? "–" : nf0.format(v));
export const num1 = (v: number | null | undefined) => (v == null ? "–" : nf1.format(v));
export const usd = (v: number | null | undefined) => (v == null ? "–" : `$${money.format(v)}`);
export const pct = (v: number | null | undefined) => (v == null ? "–" : `%${nf0.format(v)}`);
export const date = (v: string | null | undefined) => (v ? dateFmt.format(new Date(v)) : "–");
export const dateTime = (v: string | null | undefined) => (v ? dateTimeFmt.format(new Date(v)) : "–");

export const BAND_LABEL: Record<Band, string> = {
  ok: "İyi durumda",
  watch: "Takipte",
  critical: "Kritik",
  unknown: "Ölçüm bekliyor",
  empty: "Boş",
};

export const STATUS_LABEL: Record<PartStatus, string> = {
  in_stock: "Stokta",
  installed: "Takılı",
  in_repair: "Tamirde",
  refurbishing: "Kaplamada / yenilemede",
  quarantine: "Kontrol bekliyor",
  scrapped: "Hurda",
};

export const CATEGORY_LABEL: Record<string, string> = {
  tire: "Lastik",
  rim: "Jant",
  hyd_cylinder: "Hidrolik silindir",
  hyd_pump: "Hidrolik pompa",
  battery: "Akü",
  filter: "Filtre",
};
export const categoryLabel = (code: string) => CATEGORY_LABEL[code] ?? code;

export const EVENT_LABEL: Record<string, string> = {
  received: "Depoya alındı",
  installed: "Takıldı",
  removed: "Söküldü",
  inspected: "Kontrol edildi",
  repaired: "Tamir edildi",
  refurbished: "Kaplamadan / yenilemeden döndü",
  rotated: "Rotasyon",
  transferred: "Aktarıldı",
  scrapped: "Hurdaya ayrıldı",
  note: "Not",
};

export const REMOVE_REASONS: [string, string][] = [
  ["worn_out", "Aşınma (ömür sonu)"],
  ["cut", "Kesik / yırtık"],
  ["impact", "Darbe hasarı"],
  ["separation", "Ayrışma"],
  ["pressure_loss", "Basınç kaybı"],
  ["leak", "Sızıntı"],
  ["rotation", "Rotasyon"],
  ["other", "Diğer"],
];
export const reasonLabel = (code: string | null) =>
  code === "ndt" ? "NDT muayenesi" : (REMOVE_REASONS.find(([c]) => c === code)?.[1] ?? code ?? "");

export const NEXT_STATUS: [PartStatus, string][] = [
  ["in_stock", "Depoya (tekrar kullanılabilir)"],
  ["in_repair", "Tamire"],
  ["refurbishing", "Kaplamaya / yenilemeye"],
  ["quarantine", "Kontrol bekliyor"],
  ["scrapped", "Hurdaya"],
];

export const ANGLE_LABEL: Record<string, string> = {
  tread: "Taban",
  sidewall: "Yanak",
  damage_closeup: "Hasar (yakın çekim)",
};
export const angleLabel = (a: string | null) => (a ? (ANGLE_LABEL[a] ?? a) : "Fotoğraf");

export const LAYOUT_LABEL: Record<string, string> = {
  loader: "Lastikli yükleyici",
  reach_stacker: "Reach stacker",
  forklift: "Forklift",
  generic: "Genel",
};
