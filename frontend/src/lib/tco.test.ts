import { describe, expect, it } from "vitest";
import { hoursPartial, rateFromInput, sharePct, tcoSegments } from "./tco";

const costs = { parts_cost: 600, consumables_cost: 100, labor_cost: 0, external_cost: 50, downtime_cost: 250, total: 1000 };

describe("tcoSegments", () => {
  it("sıfır kalemleri atar, sırayı korur, payları toplar", () => {
    const s = tcoSegments(costs);
    expect(s.map((x) => x.key)).toEqual(["parts_cost", "consumables_cost", "external_cost", "downtime_cost"]);
    expect(s.map((x) => x.share)).toEqual([0.6, 0.1, 0.05, 0.25]);
  });
  it("API'den metin gelen sayıları okur", () => {
    const s = tcoSegments({ ...costs, parts_cost: "600.00", consumables_cost: "400.0000", external_cost: 0, downtime_cost: 0 } as never);
    expect(s.map((x) => x.share)).toEqual([0.6, 0.4]);
  });
  it("maliyet yoksa boş döner", () => {
    expect(tcoSegments({ parts_cost: 0, consumables_cost: 0, labor_cost: 0, external_cost: 0, downtime_cost: 0, total: 0 })).toEqual([]);
  });
});

describe("sharePct", () => {
  it("yüzdeyi yuvarlar, çok küçük payı gizlemez", () => {
    expect(sharePct(0.624)).toBe("%62");
    expect(sharePct(0.004)).toBe("<%1");
    expect(sharePct(0)).toBe("%0");
  });
});

describe("rateFromInput", () => {
  it("boş alan makineye özel oranı kaldırır, sıfır geçerli bir orandır", () => {
    expect(rateFromInput("  ")).toBeNull();
    expect(rateFromInput("0")).toBe(0);
    expect(rateFromInput("412,5")).toBe(412.5);
  });
  it("geçersiz ya da sınır dışı değeri reddeder", () => {
    expect(rateFromInput("abc")).toBeUndefined();
    expect(rateFromInput("-1")).toBeUndefined();
    expect(rateFromInput("100001")).toBeUndefined();
  });
});

describe("hoursPartial", () => {
  const from = "2026-01-01T00:00:00Z";
  it("saat kaydı dönem başını kapsıyorsa tam", () => {
    expect(hoursPartial({ hours_from: from }, from)).toBe(false);
    expect(hoursPartial({ hours_from: "2026-01-05T00:00:00Z" }, from)).toBe(false);
    expect(hoursPartial({ hours_from: null }, from)).toBe(false);
  });
  it("kayıt dönem içinde başlıyorsa eksik", () => {
    expect(hoursPartial({ hours_from: "2026-06-01T00:00:00Z" }, from)).toBe(true);
  });
});
