import { describe, expect, it } from "vitest";
import type { PartSupplierStat } from "../api/types";
import { OTHER_COLOR, lastBuys, onTimeShare, shareSegments, supplierColors, verdict } from "./suppliers";

const stat = (id: string, over: Partial<PartSupplierStat> = {}): PartSupplierStat => ({
  supplier_id: id, supplier_name: id.toUpperCase(), order_count: 1, spend: 100, delivered: 1, avg_lead_days: 7, timed: 1, on_time: 1,
  short: 0, qty: 1, avg_cost: 100, last_cost: 100, last_ordered_at: "2026-10-01T00:00:00Z", cheapest: false, fastest: false, ...over,
});

describe("supplierColors", () => {
  it("rengi listedeki yere göre verir; altıncıdan sonrası nötr", () => {
    const all = ["a", "b", "c", "d", "e", "f", "g"].map((supplier_id) => ({ supplier_id }));
    const c = supplierColors(all);
    expect(c.get("a")).toBe("var(--tco-1)");
    expect(c.get("e")).toBe("var(--tco-5)");
    expect(c.get("f")).toBe(OTHER_COLOR);
    // Süzgeç tedarikçi sayısını değiştirse de kalanların rengi aynı kalır
    expect(supplierColors(all).get("c")).toBe(c.get("c"));
  });
});

describe("shareSegments ve onTimeShare", () => {
  it("sıfır değerlileri atar, payları toplar", () => {
    const rows = [stat("a", { order_count: 5 }), stat("b", { order_count: 0 }), stat("c", { order_count: 2 })];
    const segs = shareSegments(rows, (r) => r.order_count, supplierColors(rows));
    expect(segs.map((s) => s.id)).toEqual(["a", "c"]);
    expect(segs[0]!.share).toBeCloseTo(5 / 7);
    expect(segs[1]!.color).toBe("var(--tco-3)");
  });
  it("ölçülebilen teslimat yoksa oran yok", () => {
    expect(onTimeShare({ on_time: 3, timed: 4 })).toBe(0.75);
    expect(onTimeShare({ on_time: 0, timed: 0 })).toBeNull();
  });
});

describe("verdict", () => {
  it("tek tedarikçide karşılaştırma yapmaz", () => {
    expect(verdict({ suppliers: [stat("a")] })).toMatch(/Tek tedarikçiden/);
  });
  it("ucuz ve hızlı ayrı tedarikçilerse ikisini de söyler", () => {
    const v = verdict({ suppliers: [
      stat("volvo", { avg_cost: 85.21, avg_lead_days: 6.75, fastest: true }),
      stat("ege", { avg_cost: 78.5, avg_lead_days: 14.5, cheapest: true }),
    ] });
    expect(v).toBe("EGE %8 daha ucuz; VOLVO ortalama 8 gün daha hızlı teslim ediyor.");
  });
  it("aynı tedarikçi hem ucuz hem hızlıysa tek cümle", () => {
    const v = verdict({ suppliers: [
      stat("ege", { avg_cost: 4.05, avg_lead_days: 3.3, cheapest: true, fastest: true }),
      stat("volvo", { avg_cost: 4.6, avg_lead_days: 6 }),
    ] });
    expect(v).toBe("EGE hem %12 daha ucuz hem ortalama 3 gün daha hızlı.");
  });
  it("teslimat ölçülemiyorsa yalnızca fiyatı söyler; fark yoksa öyle der", () => {
    expect(verdict({ suppliers: [stat("a", { cheapest: true, avg_cost: 90, avg_lead_days: null }), stat("b", { avg_lead_days: null })] }))
      .toMatch(/^A %10 daha ucuz\. Teslim süresini/);
    expect(verdict({ suppliers: [stat("a"), stat("b")] })).toBe("Fiyat ve teslim süresinde belirgin fark yok.");
  });
});

describe("lastBuys", () => {
  it("sipariş anı için kısa özet üretir", () => {
    expect(lastBuys({ suppliers: [stat("a", { avg_cost: 85.2, avg_lead_days: 6.75, order_count: 5 }), stat("b", { avg_lead_days: null })] }))
      .toBe("A $85,20 · 7 gün (5 alım)  |  B $100,00 (1 alım)");
    expect(lastBuys(undefined)).toBe("");
  });
});
