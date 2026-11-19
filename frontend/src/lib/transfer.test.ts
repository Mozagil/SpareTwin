import { describe, expect, it } from "vitest";
import { daysLeft, normalizeTransferCode, transferLabel, transferTone } from "./transfer";

describe("normalizeTransferCode", () => {
  it("boşluk, küçük harf ve eksik öneki düzeltir", () => {
    expect(normalizeTransferCode("dv 3fa9 c1b2e4")).toBe("DV-3FA9C1B2E4");
    expect(normalizeTransferCode("3fa9c1b2e4")).toBe("DV-3FA9C1B2E4");
    expect(normalizeTransferCode(" DV-3FA9C1B2E4 ")).toBe("DV-3FA9C1B2E4");
    expect(normalizeTransferCode("   ")).toBe("");
  });
});

describe("daysLeft", () => {
  const now = new Date("2026-11-19T09:00:00Z");
  it("kalan günü, son günü ve süresi dolanı ayırır", () => {
    expect(daysLeft("2026-12-19T09:00:00Z", now)).toBe("30 gün");
    expect(daysLeft("2026-11-19T20:00:00Z", now)).toBe("bugün");
    expect(daysLeft("2026-12-19T08:00:00Z", now)).toBe("30 gün");   // yeni üretilen kod "29 gün" görünmesin
    expect(daysLeft("2026-11-19T08:59:00Z", now)).toBeNull();
  });
});

describe("transferLabel", () => {
  it("kabul edilen devri tarafa göre adlandırır", () => {
    expect(transferLabel({ status: "accepted", direction: "out" })).toBe("Devredildi");
    expect(transferLabel({ status: "accepted", direction: "in" })).toBe("Devralındı");
    expect(transferLabel({ status: "expired", direction: "out" })).toBe("Süresi doldu");
    expect(transferTone("pending")).toBe("t-watch");
  });
});
