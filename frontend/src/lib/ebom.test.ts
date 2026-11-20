import { describe, expect, it } from "vitest";
import { EMPTY_RULE, buildRule, ebomState, matchKinds } from "./ebom";

describe("buildRule", () => {
  it("fire payı: tip eşleşmesi ve virgüllü yüzde", () => {
    expect(buildRule({ ...EMPTY_RULE, matchCategory: "sheet", pct: "2,5" })).toEqual({
      body: { action: "scrap", match_part_id: null, match_category: "sheet", scrap_pct: 2.5 },
    });
    expect(buildRule({ ...EMPTY_RULE, matchCategory: "sheet", pct: "0" })).toHaveProperty("error");
    expect(buildRule({ ...EMPTY_RULE })).toEqual({ error: "Eşleşecek parça tipini seçin" });
  });

  it("sarf ekle: ürün başına tüm ürünlere; birim başına eşleşme ister", () => {
    const f = { ...EMPTY_RULE, action: "add" as const, match: "all" as const, target: "p1", qty: "0,5" };
    expect(buildRule(f)).toEqual({
      body: { action: "add", match_part_id: null, match_category: null, target_part_id: "p1", qty: 0.5, per: "product" },
    });
    expect(buildRule({ ...f, per: "match" })).toHaveProperty("error");
    expect(buildRule({ ...f, target: "" })).toEqual({ error: "Eklenecek kalemi seçin" });
  });

  it("değiştir yalnızca tek kalemle eşleşir; kalem kendisiyle değişmez", () => {
    expect(matchKinds("substitute")).toEqual(["part"]);
    // Formda başka eşleşme seçili kalsa da tek kaleme düşer
    const f = { ...EMPTY_RULE, action: "substitute" as const, match: "category" as const, matchPart: "a", target: "b" };
    expect(buildRule(f)).toEqual({
      body: { action: "substitute", match_part_id: "a", match_category: null, target_part_id: "b", qty: 1 },
    });
    expect(buildRule({ ...f, target: "a" })).toEqual({ error: "Kalem kendisiyle değiştirilemez" });
  });

  it("çıkar ve düzleştir 'tümü' ile kurulamaz", () => {
    expect(matchKinds("exclude")).not.toContain("all");
    expect(buildRule({ ...EMPTY_RULE, action: "flatten", match: "all", matchCategory: "assembly" })).toEqual({
      body: { action: "flatten", match_part_id: null, match_category: "assembly" },
    });
  });
});

describe("ebomState", () => {
  it("boş, dönüştürülmemiş, güncel ve farklı durumları ayırır", () => {
    expect(ebomState({ line_count: 0, mbom_id: null, in_sync: false }).label).toBe("boş");
    expect(ebomState({ line_count: 3, mbom_id: null, in_sync: false }).label).toBe("dönüştürülmedi");
    expect(ebomState({ line_count: 3, mbom_id: "m", in_sync: true })).toEqual({ label: "üretim ağacı güncel", tone: "t-ok" });
    expect(ebomState({ line_count: 3, mbom_id: "m", in_sync: false }).label).toBe("fark var");
  });
});
