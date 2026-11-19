import { describe, expect, it } from "vitest";
import { barWidth, prematureShare, reasonMix } from "./reasons";

describe("sökme sebebi raporu", () => {
  it("sebep dağılımını Türkçe etiketlerle yazar", () => {
    expect(reasonMix({ worn_out: 3, cut: 2 })).toBe("Aşınma (ömür sonu) 3 · Kesik / yırtık 2");
    expect(reasonMix({})).toBe("");
  });
  it("aşınma dışı sökmelerin payını verir", () => {
    const reasons = [{ reason: "worn_out", count: 6, avg_part_hours: 5700 }, { reason: "cut", count: 4, avg_part_hours: 2475 }];
    expect(prematureShare({ total: 10, reasons })).toBe(0.4);
    expect(prematureShare({ total: 4, reasons: [reasons[1]!] })).toBe(1);
    expect(prematureShare({ total: 0, reasons: [] })).toBeNull();
  });
  it("çubuk genişliğini en sık sebebe göre ölçekler", () => {
    expect(barWidth(6, 6)).toBe(100);
    expect(barWidth(3, 6)).toBe(50);
    expect(barWidth(1, 400)).toBe(2);
    expect(barWidth(0, 0)).toBe(0);
  });
});
