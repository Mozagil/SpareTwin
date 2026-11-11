// Firma eşikleri: arayüz doğrulaması. Aynı sınırlar API'de de uygulanır (tenant_settings.py).
import type { Thresholds } from "../api/types";

export const THRESHOLD_FIELDS: { key: keyof Thresholds; label: string; hint: string; unit: string; min: number; max: number }[] = [
  { key: "critical_pct", label: "Kritik eşiği", unit: "%", min: 1, max: 95,
    hint: "Kalan diş / ömür bu yüzdenin altına inince parça kritik olur, bildirim ve raporda öne çıkar" },
  { key: "watch_pct", label: "İzleme eşiği", unit: "%", min: 2, max: 99,
    hint: "Bu yüzdenin altında parça izlemeye alınır (sarı). Kritik eşiğinden büyük olmalı" },
  { key: "rim_due_soon_pct", label: "Jant muayenesi yaklaşıyor", unit: "%", min: 50, max: 99,
    hint: "NDT periyodunun bu kadarı dolunca jant 'yaklaşıyor' olur. Örn. 4.000 saatlik periyotta %90 = 3.600 saat" },
  { key: "inspection_interval_days", label: "Kontrol aralığı", unit: "gün", min: 1, max: 365,
    hint: "Bu kadar gün saha kontrolü yapılmayan makine bildirilir" },
  { key: "need_horizon_hours", label: "Değişim ufku", unit: "saat", min: 24, max: 20000,
    hint: "Bu kadar saat içinde ömrü biten takılı parça sipariş ihtiyacına girer (Satınalma › İhtiyaç)" },
  { key: "maint_warn_hours", label: "Bakım yaklaşıyor (saat)", unit: "saat", min: 1, max: 2000,
    hint: "Saat bazlı bakıma bu kadar saat kala 'yaklaşıyor' olur; bildirim ve dashboard'da görünür" },
  { key: "maint_warn_days", label: "Bakım yaklaşıyor (gün)", unit: "gün", min: 1, max: 90,
    hint: "Takvim bazlı bakıma bu kadar gün kala 'yaklaşıyor' olur" },
  { key: "downtime_cost_per_hour", label: "Duruş saat maliyeti", unit: "$/saat", min: 0, max: 100000,
    hint: "Arızalı makinenin saat başı kaybı. Maliyet raporunda duruş süresi bu değerle çarpılır; 0 ise duruş maliyeti hesaplanmaz" },
];

export type ThresholdForm = Record<keyof Thresholds, string>;

export const toForm = (t: Thresholds): ThresholdForm => ({
  critical_pct: String(t.critical_pct),
  watch_pct: String(t.watch_pct),
  rim_due_soon_pct: String(t.rim_due_soon_pct),
  inspection_interval_days: String(t.inspection_interval_days),
  need_horizon_hours: String(t.need_horizon_hours),
  maint_warn_hours: String(t.maint_warn_hours),
  maint_warn_days: String(t.maint_warn_days),
  downtime_cost_per_hour: String(t.downtime_cost_per_hour),
});

const parse = (s: string) => {
  const n = Number(s.trim().replace(",", "."));
  return s.trim() === "" || Number.isNaN(n) ? null : n;
};

/** Hatalar alan adına göre; boşsa form geçerli ve `values` doludur. */
export function validateThresholds(f: ThresholdForm): { errors: Partial<ThresholdForm>; values: Thresholds | null } {
  const errors: Partial<ThresholdForm> = {};
  const out: Partial<Thresholds> = {};
  for (const d of THRESHOLD_FIELDS) {
    const v = parse(f[d.key]);
    if (v === null) errors[d.key] = "Sayı girin";
    else if (v < d.min || v > d.max) errors[d.key] = `${d.min} ile ${d.max} arasında olmalı`;
    else out[d.key] = v;
  }
  if (out.critical_pct != null && out.watch_pct != null && out.critical_pct >= out.watch_pct) {
    errors.critical_pct = "Kritik eşiği izleme eşiğinden küçük olmalı";
  }
  return { errors, values: Object.keys(errors).length ? null : (out as Thresholds) };
}

/** Denetim kaydı satırını kısa Türkçe cümleye çevirir. */
export const ENTITY_LABEL: Record<string, string> = {
  auth: "Oturum", parts: "Parça", assets: "Makine", stock: "Stok", inspections: "Kontrol", organization: "Firma ayarları",
  notifications: "Bildirim", registry: "Kayıt", imports: "İçe aktarma", images: "Görsel", labels: "Etiket", catalog: "Katalog",
  sites: "Saha", rims: "Jant", purchasing: "Satınalma", maintenance: "Bakım",
};
export const ACTION_LABEL: Record<string, string> = {
  login: "giriş yaptı", password: "parola değiştirdi", create: "oluşturdu", update: "güncelledi", delete: "sildi",
  install: "taktı", remove: "söktü", move: "yer değiştirdi", rotate: "rotasyon yaptı", events: "olay kaydetti",
  meter: "motor saati girdi", state: "bildirim durumu değiştirdi", complete: "kontrolü tamamladı", cancel: "kontrolü iptal etti",
  measurements: "ölçüm girdi", photos: "fotoğraf yükledi", movements: "stok hareketi girdi", image: "görsel yükledi",
  commit: "içe aktardı", preview: "içe aktarma önizledi", status: "durum değiştirdi", receive: "teslim aldı",
};
export const describeAudit = (entity: string | null, action: string | null) =>
  `${ENTITY_LABEL[entity ?? ""] ?? entity ?? ""} · ${ACTION_LABEL[action ?? ""] ?? action ?? ""}`.replace(/^ · | · $/g, "");
