import { describe, expect, it } from "vitest";
import type { MaintenanceDue } from "../api/types";
import { downtime, dueLeft, dueProgress, dueWhy, intervalLabel } from "./maintenance";

const base: MaintenanceDue = {
  plan_id: "p", name: "500 saat periyodik bakım", interval_hours: 500, interval_days: null, checklist: [],
  asset_id: "a", asset_code: "LD-07", meter_hours: 12480, asset_status: "active", site_id: null,
  last_done_at: "2026-09-10T10:00:00Z", last_done_hours: 12000, last_done_number: "BK-2026-0001",
  next_due_hours: 12500, next_due_at: null, hours_left: 20, days_left: null, hours_per_day: 8, eta_at: "2026-11-12",
  state: "due_soon", open_work_order_id: null, open_work_order_number: null, open_work_order_status: null,
};

describe("bakım cümleleri", () => {
  it("saat bazlı: son bakım, sıradaki ve kalan saat, tahmini tarih", () => {
    expect(dueLeft(base)).toBe("20 saat kaldı (yaklaşık 12 Kas 2026)");
    expect(dueWhy(base)).toBe("Son bakım 12.000 saatte; sıradaki 12.500 saatte, 20 saat kaldı (yaklaşık 12 Kas 2026).");
  });
  it("gecikmişi ve takvim bazlıyı anlatır", () => {
    expect(dueLeft({ ...base, hours_left: -40, eta_at: null })).toBe("40 saat geçti");
    const cal = { ...base, interval_hours: null, interval_days: 180, last_done_hours: null, last_done_at: null,
                  next_due_hours: null, hours_left: null, next_due_at: "2026-11-14", days_left: 5, eta_at: "2026-11-14" };
    expect(dueWhy(cal)).toBe("Hiç yapılmadı; tarih 14 Kas 2026, 5 gün kaldı.");
    expect(dueLeft({ ...cal, days_left: 0 })).toBe("bugün");
  });
  it("ilerleme ve periyot etiketi", () => {
    expect(dueProgress(base)).toBeCloseTo(0.96, 2);
    expect(dueProgress({ ...base, hours_left: -40 })).toBe(1);
    expect(intervalLabel({ interval_hours: 500, interval_days: 180 })).toBe("500 saat / 180 gün");
    expect(intervalLabel({ interval_hours: null, interval_days: 30 })).toBe("30 gün");
  });
});

describe("duruş süresi", () => {
  it("dakikayı saat ve dakikaya çevirir", () => {
    expect(downtime(330)).toBe("5 sa 30 dk");
    expect(downtime(120)).toBe("2 sa");
    expect(downtime(45)).toBe("45 dk");
    expect(downtime(null)).toBe("–");
    expect(downtime(0)).toBe("–");
  });
});
