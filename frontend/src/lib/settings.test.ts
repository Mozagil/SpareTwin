import { describe, expect, it } from "vitest";
import { describeAudit, toForm, validateThresholds } from "./settings";

const ok = { critical_pct: 20, watch_pct: 40, rim_due_soon_pct: 90, inspection_interval_days: 30 };

describe("eşik doğrulama", () => {
  it("varsayılanlar geçerlidir", () => {
    const r = validateThresholds(toForm(ok));
    expect(r.errors).toEqual({});
    expect(r.values).toEqual(ok);
  });
  it("Türkçe ondalık okunur, sınır dışı ve boş değer hata verir", () => {
    const r = validateThresholds({ ...toForm(ok), critical_pct: "12,5", inspection_interval_days: "0", rim_due_soon_pct: "" });
    expect(r.values).toBeNull();
    expect(r.errors.critical_pct).toBeUndefined();
    expect(r.errors.inspection_interval_days).toMatch(/1 ile 365/);
    expect(r.errors.rim_due_soon_pct).toBe("Sayı girin");
  });
  it("kritik eşiği izleme eşiğinden küçük olmalı", () => {
    const r = validateThresholds({ ...toForm(ok), critical_pct: "40", watch_pct: "40" });
    expect(r.values).toBeNull();
    expect(r.errors.critical_pct).toMatch(/küçük/);
  });
});

describe("denetim kaydı açıklaması", () => {
  it("bilinen varlık ve eylemi Türkçeleştirir, bilinmeyeni olduğu gibi bırakır", () => {
    expect(describeAudit("parts", "install")).toBe("Parça · taktı");
    expect(describeAudit("auth", "login")).toBe("Oturum · giriş yaptı");
    expect(describeAudit("foo", "bar")).toBe("foo · bar");
    expect(describeAudit(null, "login")).toBe("giriş yaptı");
  });
});
