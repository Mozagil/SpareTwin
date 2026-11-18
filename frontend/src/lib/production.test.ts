import { describe, expect, it } from "vitest";
import type { ProductLine } from "../api/types";
import { deviation, duration, flatten, leafTotals, waste } from "./production";

describe("waste", () => {
  it("fazla kullanım fire, az kullanım tasarruf", () => {
    expect([waste(2, 3), waste("5", "4.5"), waste(4, 4)]).toEqual([{ diff: 1, pct: 50 }, { diff: -0.5, pct: -10 }, { diff: 0, pct: 0 }]);
  });
  it("kayan nokta artığı bırakmaz", () => {
    expect(waste(0.1, 0.3).diff).toBe(0.2);
  });
});

describe("duration", () => {
  it("dakikayı saat ve dakikaya çevirir", () => {
    expect([duration(135), duration(40), duration(120), duration("59.6")]).toEqual(["2 sa 15 dk", "40 dk", "2 sa", "1 sa"]);
  });
  it("boş ve çok kısa süre", () => {
    expect([duration(null), duration(0), duration(0.4)]).toEqual(["–", "0 dk", "1 dk'dan az"]);
  });
});

describe("deviation", () => {
  it("plana göre yüzde", () => {
    expect([deviation(120, 150), deviation(120, 90), deviation("100", "100")]).toEqual([25, -25, 0]);
  });
  it("plan yoksa null", () => {
    expect([deviation(null, 50), deviation(0, 50)]).toEqual([null, null]);
  });
});

const line = (part_id: string, total_qty: number, children: ProductLine[] = []): ProductLine => ({
  line_id: 1, part_id, name: part_id, part_no: null, unit: "adet", category_code: "filter", notes: null,
  qty: total_qty, total_qty, in_stock: 3, unit_cost: 1, cost: total_qty, unknown_cost: 0, has_bom: children.length > 0, children,
});

const tree = [line("sub", 2, [line("seal", 2), line("oil", 5)]), line("oil", 1)];

describe("flatten", () => {
  it("ağacı derinlik sırasıyla açar", () => {
    expect(flatten(tree).map((r) => [r.part_id, r.depth])).toEqual([["sub", 0], ["seal", 1], ["oil", 1], ["oil", 0]]);
  });
  it("kapalı alt montajın çocuklarını atlar", () => {
    expect(flatten(tree, new Set(["/sub"])).map((r) => r.part_id)).toEqual(["sub", "oil"]);
  });
  it("aynı kalem farklı dalda ayrı yol alır", () => {
    expect(flatten(tree).filter((r) => r.part_id === "oil").map((r) => r.path)).toEqual(["/sub/oil", "/oil"]);
  });
});

describe("leafTotals", () => {
  it("yaprakları kalem bazında toplar, alt montajı saymaz", () => {
    expect(leafTotals(tree).map((r) => [r.part_id, r.qty])).toEqual([["seal", 2], ["oil", 6]]);
  });
});
