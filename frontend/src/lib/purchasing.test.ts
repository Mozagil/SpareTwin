import { describe, expect, it } from "vitest";
import type { PurchaseNeed } from "../api/types";
import { lineTotal, needItemLabel, needWhy, orderProgress } from "./purchasing";

const need: PurchaseNeed = {
  part_id: "p1", name: "29.5R25 L-4 radyal", manufacturer: "Michelin", part_no: null, unit: "adet", category_code: "tire",
  is_serialized: true, min_stock: 2, in_stock: 1, avg_cost: 9800, upcoming: 2,
  items: [
    { id: "a", asset_code: "LD-07", position: "A2-L", band: "critical", condition_pct: 13, hours_left: 539 },
    { id: "b", asset_code: "LD-07", position: "A2-R", band: "watch", condition_pct: 28, hours_left: 420 },
  ],
  on_order: 0, requested: 0, need: 3,
};

describe("needWhy", () => {
  it("yaklaşan değişimi makine ve stokla anlatır", () => {
    expect(needWhy(need)).toBe("LD-07 için 2 lastik yaklaşıyor, stokta 1 var.");
    expect(needWhy({ ...need, on_order: 2, requested: 1, in_stock: 0 }))
      .toBe("LD-07 için 2 lastik yaklaşıyor, stokta yok, siparişte 2, talepte 1.");
  });
  it("yalnızca kritik seviye altıysa seviyeyi söyler", () => {
    expect(needWhy({ ...need, upcoming: 0, items: null, min_stock: 6, in_stock: 4, unit: "adet" }))
      .toBe("Kritik seviye 6 adet, stokta 4 var.");
  });
  it("parça etiketi kritikte yüzdeyi, diğerinde kalan saati gösterir", () => {
    expect(needItemLabel(need.items![0])).toBe("LD-07 A2-L · %13");
    expect(needItemLabel(need.items![1])).toBe("LD-07 A2-R · 420 saat");
  });
});

describe("sipariş hesapları", () => {
  it("satır tutarı ve teslim oranı", () => {
    expect(lineTotal({ qty: 5, unit_cost: 83 })).toBe(415);
    expect(lineTotal({ qty: 5, unit_cost: null })).toBeNull();
    expect(orderProgress([{ qty: 10, received_qty: 3 }, { qty: 2, received_qty: 2 }])).toBeCloseTo(5 / 12);
    expect(orderProgress([])).toBe(0);
  });
});
