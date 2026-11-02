import { describe, expect, it } from "vitest";
import type { SheetItem } from "../api/types";
import { itemState, nextIncomplete, rangeWarning } from "./inspection";

const tread = { metric: "tread_depth_mm", label: "Diş derinliği", unit: "mm", required: true, min: 0, max: 200 };

describe("rangeWarning", () => {
  it("boş değerde uyarı yok, sayı olmayanda uyarı", () => {
    expect(rangeWarning(tread, "")).toBeNull();
    expect(rangeWarning(tread, "abc")).toBe("Sayı girin");
  });
  it("Türkçe ondalık virgülü kabul eder", () => {
    expect(rangeWarning(tread, "12,5", 14)).toBeNull();
  });
  it("aralık dışını yakalar", () => {
    expect(rangeWarning(tread, "999")).toMatch(/En fazla 200 mm/);
  });
  it("diş derinliği öncekinden belirgin fazlaysa uyarır (yanlış ölçüm şüphesi)", () => {
    expect(rangeWarning(tread, "20", 14)).toMatch(/diş derinliği artmaz/);
    expect(rangeWarning(tread, "15", 14)).toBeNull(); // ölçüm toleransı
  });
});

const item = (position: string, o: Partial<SheetItem>): SheetItem => ({
  position, label: position, category_code: "tire", x: 0, y: 0, part_item_id: position, serial_no: null, part_name: "L",
  profile: [], required_angles: [], values: {}, previous: {}, photos: [], missing: [], required: true, started: false, complete: false, ...o,
});

describe("akış yardımcıları", () => {
  const items = [
    item("A1-L", { complete: true, started: true }),
    item("A1-R", {}),
    item("A2-L", { started: true }),
    item("CYL", { required: false }),
  ];
  it("sıradaki eksik pozisyonu bulur, sona gelince başa döner", () => {
    expect(nextIncomplete(items)?.position).toBe("A1-R");
    expect(nextIncomplete(items, "A1-R")?.position).toBe("A2-L");
    expect(nextIncomplete(items, "A2-L")?.position).toBe("A1-R");
  });
  it("durumları ayırt eder", () => {
    expect(items.map(itemState)).toEqual(["done", "todo", "partial", "optional"]);
  });
});
