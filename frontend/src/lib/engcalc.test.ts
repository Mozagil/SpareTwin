import { describe, expect, it } from "vitest";
import { bend, cylinder, suggestK, type BendResult, type CylinderResult } from "./engcalc";

describe("bend", () => {
  it("2 mm sac, R2, 90°, K 0,4: bilinen değerler", () => {
    const r = bend({ thickness: 2, radius: 2, angle: 90, kFactor: 0.4, flangeA: 50, flangeB: 30 }) as BendResult;
    expect(r.allowance).toBeCloseTo(4.398, 3);      // π/2 × (2 + 0,4×2)
    expect(r.setback).toBeCloseTo(4, 6);            // (R + T) × tan 45°
    expect(r.deduction).toBeCloseTo(3.602, 3);
    expect(r.flat).toBeCloseTo(76.398, 3);
    expect(r.kSuggested).toBe(false);
    expect(r.warnings).toEqual([]);
  });

  it("K girilmezse R/T oranından önerir", () => {
    expect([suggestK(1, 2), suggestK(2, 2), suggestK(6, 2)]).toEqual([0.33, 0.4, 0.5]);
    const r = bend({ thickness: 3, radius: 1, angle: 90, flangeA: 40, flangeB: 40 }) as BendResult;
    expect(r.kFactor).toBe(0.33);
    expect(r.kSuggested).toBe(true);
    expect(r.warnings[0]).toContain("çatlama");
  });

  it("geçersiz girdiyi nedeniyle reddeder, 90° üzerini uyarır", () => {
    expect(bend({ thickness: 0, radius: 2, angle: 90, flangeA: 10, flangeB: 10 })).toHaveProperty("error");
    expect(bend({ thickness: 2, radius: 2, angle: 180, flangeA: 10, flangeB: 10 })).toHaveProperty("error");
    expect(bend({ thickness: 2, radius: 2, angle: 90, kFactor: 0.7, flangeA: 10, flangeB: 10 })).toHaveProperty("error");
    const r = bend({ thickness: 2, radius: 4, angle: 120, flangeA: 80, flangeB: 80 }) as BendResult;
    expect(r.warnings.some((w) => w.includes("90°"))).toBe(true);
  });
});

describe("cylinder", () => {
  it("Ø100 / Ø56, 200 bar, 500 mm strok, 10 s", () => {
    const r = cylinder({ bore: 100, rod: 56, pressure: 200, stroke: 500, extendSeconds: 10 }) as CylinderResult;
    expect(r.pistonArea).toBeCloseTo(78.54, 2);
    expect(r.annulusArea).toBeCloseTo(53.91, 2);
    expect(r.pushKn).toBeCloseTo(157.08, 2);
    expect(r.pullKn).toBeCloseTo(107.82, 2);
    expect(r.pushTon).toBeCloseTo(16.02, 2);
    expect(r.extendSpeed).toBe(50);
    expect(r.flowLpm).toBeCloseTo(23.56, 2);
    // Aynı debiyle kapanma daha hızlıdır (halka alanı küçük)
    expect(r.retractSeconds).toBeCloseTo(6.864, 3);
    expect(r.strokeLitres).toBeCloseTo(3.927, 3);
    expect(r.warnings).toEqual([]);
  });

  it("mil pistondan kalın olamaz; uzun strok ve yüksek basınç uyarır", () => {
    expect(cylinder({ bore: 50, rod: 50, pressure: 100, stroke: 100, extendSeconds: 5 })).toHaveProperty("error");
    const r = cylinder({ bore: 63, rod: 36, pressure: 400, stroke: 1200, extendSeconds: 2 }) as CylinderResult;
    expect(r.warnings).toHaveLength(3);
  });
});
