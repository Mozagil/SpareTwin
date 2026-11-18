import { describe, expect, it } from "vitest";
import {
  buildProfile, buildTemplate, emptyMetric, newPosition, nextCode, nudge, positionCode, slugify, svgToPct,
  toTemplateDraft, withRimSlots, type PositionDraft,
} from "./library";

const pos = (code: string, over: Partial<PositionDraft> = {}): PositionDraft =>
  ({ key: Math.random(), code, label: code, category_code: "tire", axle: "1", x: 20, y: 30, ...over });

describe("slugify ve positionCode", () => {
  it("Türkçe adı kalıcı koda çevirir", () => {
    expect(slugify("Şanzıman / dişli kutusu")).toBe("sanziman_disli_kutusu");
    expect(slugify("10 dk çökme mm")).toBe("dk_cokme_mm");
    expect(slugify("İ")).toBe("");
  });
  it("pozisyon kodunu büyük harfe ve geçerli karakterlere indirger", () => {
    expect(positionCode("ön sol 1")).toBe("ON-SOL-1");
    expect(positionCode("lift.cyl_l")).toBe("LIFTCYL_L");
  });
});

describe("buildProfile", () => {
  it("anahtarı addan üretir, var olan anahtarı korur, boş sınırı yazmaz", () => {
    const { errors, profile } = buildProfile([
      { ...emptyMetric(), label: "Yağ sıcaklığı", unit: "°C", min: "0", max: "150", required: true },
      { ...emptyMetric(), metric: "drift_mm", label: "Çökme (yeni ad)", unit: "mm" },
    ]);
    expect(errors).toEqual([]);
    expect(profile).toEqual([
      { metric: "yag_sicakligi_c", label: "Yağ sıcaklığı", unit: "°C", required: true, min: 0, max: 150 },
      { metric: "drift_mm", label: "Çökme (yeni ad)", unit: "mm", required: false },
    ]);
  });
  it("eksik ad, yinelenen ölçüm ve ters sınırı reddeder", () => {
    expect(buildProfile([emptyMetric()]).errors).toHaveLength(1);
    expect(buildProfile([{ ...emptyMetric(), label: "Boşluk" }, { ...emptyMetric(), label: "Boşluk" }]).profile).toBeNull();
    expect(buildProfile([{ ...emptyMetric(), label: "Boşluk", min: "5", max: "1" }]).errors[0]).toMatch(/alt sınır/);
    expect(buildProfile([{ ...emptyMetric(), label: "Boşluk", min: "abc" }]).errors[0]).toMatch(/sayı/);
  });
});

describe("şablon taslağı", () => {
  it("ortak şablonu kopya olarak açar: id yok, konumlar sayı", () => {
    const d = toTemplateDraft({
      id: "t1", name: "Forklift", layout: "forklift", is_library: true, model_count: 0, image: null,
      positions: [{ code: "A1-L", label: "Ön sol", category_code: "tire", axle: 1, x: "28.00" as unknown as number, y: 26 },
                  { code: "A1-L-J", label: "Ön sol jantı", category_code: "rim", axle: 1, x: null, y: null }],
    }, true);
    expect(d.id).toBeUndefined();
    expect(d.name).toBe("Forklift (kopya)");
    expect(d.positions[0]).toMatchObject({ x: 28, y: 26, axle: "1" });
    expect(d.positions[1]).toMatchObject({ x: null, y: null });
  });
  it("sıradaki boş kodu bulur ve yeni yuvayı şemaya koyar", () => {
    expect(nextCode([{ code: "P1" }, { code: "P3" }])).toBe("P2");
    const p = newPosition([pos("P1")], "hyd_pump");
    expect(p).toMatchObject({ code: "P2", category_code: "hyd_pump", y: 50 });
    expect(p.x).not.toBeNull();
  });
  it("lastiklere jant yuvası ekler, var olanı yinelemez", () => {
    const out = withRimSlots([pos("A1-L"), pos("A1-R"), pos("A1-R-J", { category_code: "rim", x: null, y: null }), pos("PUMP", { category_code: "hyd_pump" })]);
    expect(out.map((p) => p.code)).toEqual(["A1-L", "A1-R", "A1-R-J", "PUMP", "A1-L-J"]);
    expect(out[4]).toMatchObject({ category_code: "rim", x: null, y: null, axle: "1", label: "A1-L jantı" });
  });
  it("şema koordinatını 0–100 aralığına çevirir ve sınırda tutar", () => {
    expect(svgToPct(40 + 22 * 5.6, 20 + 30 * 3.2)).toEqual({ x: 22, y: 30 });
    expect(svgToPct(-50, 9999)).toEqual({ x: 0, y: 100 });
    expect(nudge({ x: 99, y: 1 }, 5, -5)).toEqual({ x: 100, y: 0 });
    expect(nudge({ x: null, y: null }, 5, 5)).toEqual({ x: null, y: null });
  });
});

describe("buildTemplate", () => {
  it("geçerli taslağı gövdeye çevirir", () => {
    const { errors, body } = buildTemplate({ name: " Kırıcı ", layout: "generic", positions: [pos("A1-L", { label: " Ön sol " }), pos("GB", { category_code: "gearbox", axle: "", x: null, y: null })] });
    expect(errors).toEqual([]);
    expect(body).toEqual({
      name: "Kırıcı", layout: "generic",
      positions: [{ code: "A1-L", label: "Ön sol", category_code: "tire", axle: 1, x: 20, y: 30 },
                  { code: "GB", label: "GB", category_code: "gearbox", axle: null, x: null, y: null }],
    });
  });
  it("adsız şablonu, boş listeyi, yinelenen ve geçersiz kodu reddeder", () => {
    expect(buildTemplate({ name: "", layout: "generic", positions: [] }).errors).toHaveLength(2);
    const { errors, body } = buildTemplate({ name: "X1", layout: "generic", positions: [pos("A1"), pos("A1"), pos("a b"), pos("B1", { label: " " }), pos("C1", { axle: "0" })] });
    expect(body).toBeNull();
    expect(errors).toEqual([
      "A1: bu kod iki kez var", "a b: kod büyük harf, rakam ve tire içerebilir", "B1: ad girin", "C1: aks 1 ile 12 arasında olmalı",
    ]);
  });
});
