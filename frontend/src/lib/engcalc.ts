// Mühendislik hesap araçları: büküm açınımı ve hidrolik silindir. Ön kontrol içindir;
// sonuç hiçbir yere kaydedilmez, hesap tarayıcıda yapılır (K-028).

// ---------- Sac büküm ----------
export interface BendInput {
  /** Sac kalınlığı (mm) */
  thickness: number;
  /** İç büküm yarıçapı (mm) */
  radius: number;
  /** Büküm açısı (derece): düz sac 0, dik büküm 90 */
  angle: number;
  /** Nötr eksen katsayısı (0–0,5); boşsa R/T oranından önerilir */
  kFactor?: number | null;
  /** Kenar boyları, dıştan dışa (mm) */
  flangeA: number;
  flangeB: number;
}
export interface BendResult {
  kFactor: number;
  /** K önerilen değer mi (kullanıcı girmedi) */
  kSuggested: boolean;
  /** Büküm payı: bükümdeki nötr eksen yay boyu (mm) */
  allowance: number;
  /** Dış pay: teğet noktasından dış köşeye (mm) */
  setback: number;
  /** Büküm kesintisi: iki kenarın toplamından düşülecek (mm) */
  deduction: number;
  /** Açınım boyu (mm) */
  flat: number;
  warnings: string[];
}

/** Yaygın atölye kuralı: sıkı bükümde nötr eksen içe kayar. */
export const suggestK = (radius: number, thickness: number) => {
  const r = radius / thickness;
  return r < 1 ? 0.33 : r < 3 ? 0.4 : 0.5;
};

export function bend(i: BendInput): BendResult | { error: string } {
  if (!(i.thickness > 0)) return { error: "Sac kalınlığı sıfırdan büyük olmalı" };
  if (!(i.radius >= 0)) return { error: "İç yarıçap negatif olamaz" };
  if (!(i.angle > 0 && i.angle < 180)) return { error: "Büküm açısı 0 ile 180 derece arasında olmalı" };
  if (!(i.flangeA > 0 && i.flangeB > 0)) return { error: "Kenar boyları sıfırdan büyük olmalı" };
  const given = i.kFactor != null && !Number.isNaN(i.kFactor);
  const k = given ? i.kFactor! : suggestK(i.radius, i.thickness);
  if (!(k > 0 && k <= 0.5)) return { error: "K katsayısı 0 ile 0,5 arasında olmalı" };

  const rad = (i.angle * Math.PI) / 180;
  const allowance = rad * (i.radius + k * i.thickness);
  const setback = (i.radius + i.thickness) * Math.tan(rad / 2);
  const deduction = 2 * setback - allowance;
  const flat = i.flangeA + i.flangeB - deduction;

  const warnings: string[] = [];
  if (i.radius < i.thickness) warnings.push("İç yarıçap sac kalınlığından küçük: malzemeye göre çatlama riski; en küçük büküm yarıçapını kontrol edin.");
  if (i.angle > 90) warnings.push("90° üzeri bükümde dış ölçü köşeye değil teğet noktasına göre alınır; kenar boylarını buna göre girin.");
  if (Math.min(i.flangeA, i.flangeB) < setback + 2 * i.thickness) warnings.push("Kenar boyu büküm için kısa olabilir (kalıp V açıklığına sığmayabilir).");
  return { kFactor: k, kSuggested: !given, allowance, setback, deduction, flat, warnings };
}

// ---------- Hidrolik silindir ----------
export interface CylinderInput {
  /** Piston (gömlek iç) çapı (mm) */
  bore: number;
  /** Mil çapı (mm) */
  rod: number;
  /** Çalışma basıncı (bar) */
  pressure: number;
  /** Strok (mm) */
  stroke: number;
  /** İstenen itme (açılma) süresi (s) */
  extendSeconds: number;
}
export interface CylinderResult {
  /** Piston ve halka alanı (cm²) */
  pistonArea: number;
  annulusArea: number;
  /** İtme ve çekme kuvveti (kN) */
  pushKn: number;
  pullKn: number;
  /** Aynı kuvvetler ton-kuvvet olarak */
  pushTon: number;
  pullTon: number;
  /** İstenen sürede açılmak için debi (L/dk) ve hız (mm/s) */
  flowLpm: number;
  extendSpeed: number;
  /** Aynı debiyle kapanma hızı (mm/s) ve süresi (s) */
  retractSpeed: number;
  retractSeconds: number;
  /** Strok hacmi: açılırken giren yağ (L) */
  strokeLitres: number;
  warnings: string[];
}

const G = 9.80665;

export function cylinder(i: CylinderInput): CylinderResult | { error: string } {
  if (!(i.bore > 0)) return { error: "Piston çapı sıfırdan büyük olmalı" };
  if (!(i.rod > 0 && i.rod < i.bore)) return { error: "Mil çapı sıfırdan büyük ve piston çapından küçük olmalı" };
  if (!(i.pressure > 0)) return { error: "Basınç sıfırdan büyük olmalı" };
  if (!(i.stroke > 0)) return { error: "Strok sıfırdan büyük olmalı" };
  if (!(i.extendSeconds > 0)) return { error: "Süre sıfırdan büyük olmalı" };

  const piston = (Math.PI * i.bore ** 2) / 4;                    // mm²
  const annulus = (Math.PI * (i.bore ** 2 - i.rod ** 2)) / 4;    // mm²
  // 1 bar = 0,1 N/mm²
  const pushKn = (i.pressure * 0.1 * piston) / 1000;
  const pullKn = (i.pressure * 0.1 * annulus) / 1000;
  const extendSpeed = i.stroke / i.extendSeconds;                // mm/s
  const flowLpm = (piston * extendSpeed * 60) / 1e6;             // mm³/s → L/dk
  const retractSpeed = (flowLpm * 1e6) / 60 / annulus;
  const warnings: string[] = [];
  if (i.pressure > 350) warnings.push("350 bar üzeri: standart silindir ve hortum sınıflarının dışında olabilir.");
  if (extendSpeed > 500) warnings.push("Piston hızı 0,5 m/s üzerinde: keçe ömrü ve strok sonu yastıklama kontrol edilmeli.");
  if (i.stroke / i.rod > 10) warnings.push("Strok mil çapının 10 katından uzun: itmede burkulma hesabı yapılmalı.");
  return {
    pistonArea: piston / 100, annulusArea: annulus / 100,
    pushKn, pullKn, pushTon: (pushKn * 1000) / G / 1000, pullTon: (pullKn * 1000) / G / 1000,
    flowLpm, extendSpeed, retractSpeed, retractSeconds: i.stroke / retractSpeed,
    strokeLitres: (piston * i.stroke) / 1e6, warnings,
  };
}
