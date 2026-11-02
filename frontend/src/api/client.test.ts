import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { __resetForTests, api, ApiError, login, session } from "./client";

const user = { id: "u1", email: "a@b.c", full_name: "A", locale: "tr", memberships: [] };
const tokens = (n: number) => ({ access_token: `access-${n}`, refresh_token: `refresh-${n}`, token_type: "bearer", expires_in: 1800, user });
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  localStorage.clear();
  __resetForTests();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const authHeader = (call: unknown[]) => (call[1] as RequestInit).headers as Record<string, string>;

describe("api istemcisi", () => {
  it("girişten sonra token'ı başlıkta gönderir, yenileme token'ını saklar", async () => {
    fetchMock.mockResolvedValueOnce(json(200, tokens(1))).mockResolvedValueOnce(json(200, [{ id: 1 }]));
    await login("a@b.c", "x");
    expect(session.refreshToken).toBe("refresh-1");
    await api("/assets");
    expect(authHeader(fetchMock.mock.calls[1]).Authorization).toBe("Bearer access-1");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/assets");
  });

  it("401 gelince bir kez yeniler ve isteği tekrarlar", async () => {
    fetchMock
      .mockResolvedValueOnce(json(200, tokens(1)))
      .mockResolvedValueOnce(json(401, { detail: "süre doldu" }))
      .mockResolvedValueOnce(json(200, tokens(2)))
      .mockResolvedValueOnce(json(200, { ok: true }));
    await login("a@b.c", "x");
    await expect(api("/assets")).resolves.toEqual({ ok: true });
    expect(fetchMock.mock.calls[2][0]).toBe("/api/auth/refresh");
    expect(authHeader(fetchMock.mock.calls[3]).Authorization).toBe("Bearer access-2");
    expect(session.refreshToken).toBe("refresh-2"); // dönen yeni token saklandı
  });

  it("aynı anda gelen 401'ler tek yenileme yapar", async () => {
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      if (url === "/api/auth/login") return json(200, tokens(1));
      if (url === "/api/auth/refresh") return json(200, tokens(2));
      const h = init.headers as Record<string, string>;
      return h.Authorization === "Bearer access-2" ? json(200, { url }) : json(401, { detail: "x" });
    });
    await login("a@b.c", "x");
    await Promise.all([api("/a"), api("/b"), api("/c")]);
    expect(fetchMock.mock.calls.filter((c) => c[0] === "/api/auth/refresh")).toHaveLength(1);
  });

  it("yenileme reddedilirse oturumu temizler ve hata verir", async () => {
    const seen: unknown[] = [];
    session.subscribe((u) => seen.push(u));
    fetchMock
      .mockResolvedValueOnce(json(200, tokens(1)))
      .mockResolvedValueOnce(json(401, { detail: "x" }))
      .mockResolvedValueOnce(json(401, { detail: "Oturum süresi doldu" }));
    await login("a@b.c", "x");
    await expect(api("/assets")).rejects.toBeInstanceOf(ApiError);
    expect(session.refreshToken).toBeNull();
    expect(seen.at(-1)).toBeNull();
  });

  it("API hata mesajını ve alan listesini taşır", async () => {
    fetchMock.mockResolvedValueOnce(json(422, { detail: "Girilen bilgiler geçersiz", fields: [{ field: "reason", message: "gerekli" }] }));
    const err = (await api("/x", { method: "POST", body: {} }).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe("Girilen bilgiler geçersiz");
    expect(err.fields[0].field).toBe("reason");
  });

  it("API kapalıyken anlaşılır mesaj verir", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 500 })); // Vite proxy: API'ye ulaşamadı
    await expect(login("a@b.c", "x")).rejects.toThrow("Sunucuya ulaşılamıyor");
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch")); // hiç sunucu yok
    await expect(api("/assets")).rejects.toThrow("Sunucuya ulaşılamıyor");
  });

  it("seçili firmayı başlıkta gönderir, boş sorgu parametrelerini atlar", async () => {
    session.setTenant("t-1");
    fetchMock.mockResolvedValueOnce(json(200, []));
    await api("/parts", { query: { status: "in_stock", category: "", band: undefined } });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/parts?status=in_stock");
    expect(authHeader(fetchMock.mock.calls[0])["X-Tenant-Id"]).toBe("t-1");
  });
});
