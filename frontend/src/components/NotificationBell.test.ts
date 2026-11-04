import { describe, expect, it } from "vitest";
import type { Notification } from "../api/types";
import { notificationPath } from "./NotificationBell";

const n = (type: Notification["link"]["type"], id = "x1"): Notification => ({
  key: "k", kind: "part_critical", severity: "critical", title: "", body: "", link: { type, id }, at: null, read: false,
});

describe("bildirim bağlantıları", () => {
  it("her bildirim ilgili sayfaya götürür", () => {
    expect(notificationPath(n("part"))).toBe("/parca/x1");
    expect(notificationPath(n("asset"))).toBe("/makine/x1");
    expect(notificationPath(n("rim"))).toBe("/jantlar");
    expect(notificationPath(n("stock"))).toBe("/stok?kalem=x1");
  });
});
