import { describe, expect, it } from "vitest";
import type { Notification } from "../api/types";
import { notificationPath, stateLabel } from "./NotificationBell";

const n = (type: Notification["link"]["type"], id = "x1", extra: Partial<Notification> = {}): Notification => ({
  key: "k", kind: "part_critical", severity: "critical", title: "", body: "", link: { type, id }, at: null, read: false,
  state: null, state_by: null, state_at: null, note: null, ...extra,
});

describe("bildirim bağlantıları", () => {
  it("her bildirim ilgili sayfaya götürür", () => {
    expect(notificationPath(n("part"))).toBe("/parca/x1");
    expect(notificationPath(n("asset"))).toBe("/makine/x1");
    expect(notificationPath(n("rim"))).toBe("/jantlar");
    expect(notificationPath(n("stock"))).toBe("/stok?kalem=x1");
  });
});

describe("ekip durumu etiketi", () => {
  it("durum yoksa etiket yok", () => {
    expect(stateLabel(n("part"))).toBeNull();
  });
  it("üstlenen ve gizleyen kişiyi söyler", () => {
    expect(stateLabel(n("part", "x1", { state: "acknowledged", state_by: "Ayşe" }))).toBe("Ayşe üstlendi");
    expect(stateLabel(n("part", "x1", { state: "dismissed", state_by: null }))).toBe("biri gizledi");
    expect(stateLabel(n("part", "x1", { state: "acknowledged", state_by: "Ali", state_at: "2026-11-09T10:00:00Z" }))).toMatch(/^Ali üstlendi · /);
  });
});
