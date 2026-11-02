// API istemcisi.
// - Erişim token'ı yalnızca bellekte tutulur (sayfa yenilenince yenileme token'ıyla yeniden alınır).
// - Yenileme token'ı ve seçili firma localStorage'da.
// - 401 gelirse bir kez yenileme denenir; aynı anda gelen 401'ler tek yenilemeyi bekler.

import type { Me, TokenOut } from "./types";

export const API_BASE = "/api";
const REFRESH_KEY = "st.refresh";
const TENANT_KEY = "st.tenant";

export class ApiError extends Error {
  status: number;
  fields: { field: string; message: string }[];
  constructor(status: number, message: string, fields: { field: string; message: string }[] = []) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

type Listener = (user: Me | null) => void;

let accessToken: string | null = null;
let refreshing: Promise<Me | null> | null = null;
const listeners = new Set<Listener>();

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export const session = {
  get refreshToken() {
    return storage()?.getItem(REFRESH_KEY) ?? null;
  },
  get tenantId() {
    return storage()?.getItem(TENANT_KEY) ?? null;
  },
  setTenant(id: string | null) {
    if (id) storage()?.setItem(TENANT_KEY, id);
    else storage()?.removeItem(TENANT_KEY);
  },
  subscribe(fn: Listener) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
};

function setTokens(t: TokenOut | null) {
  accessToken = t?.access_token ?? null;
  if (t) storage()?.setItem(REFRESH_KEY, t.refresh_token);
  else storage()?.removeItem(REFRESH_KEY);
  listeners.forEach((l) => l(t?.user ?? null));
}

export const SERVER_DOWN = "Sunucuya ulaşılamıyor. API çalışıyor mu? (Codespace'te: make dev)";

async function parseError(res: Response): Promise<ApiError> {
  let detail = `İstek başarısız (${res.status})`;
  let fields: ApiError["fields"] = [];
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
    if (Array.isArray(body?.fields)) fields = body.fields;
  } catch {
    // Gövde JSON değil: API'miz her hatayı JSON döndürür. 5xx + JSON olmayan gövde,
    // arada bir sunucunun (Vite/Caddy) API'ye ulaşamadığı anlamına gelir.
    if (res.status >= 500) detail = SERVER_DOWN;
  }
  return new ApiError(res.status, detail, fields);
}

/** fetch ağ hatasında (sunucu hiç yok) TypeError fırlatır; anlaşılır hataya çevir. */
async function send(input: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch {
    throw new ApiError(0, SERVER_DOWN);
  }
}

export async function login(email: string, password: string): Promise<Me> {
  const res = await send(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw await parseError(res);
  const t: TokenOut = await res.json();
  setTokens(t);
  return t.user;
}

/** Yenileme token'ıyla yeni oturum. Başarısızsa oturum temizlenir ve null döner. */
export function refreshSession(): Promise<Me | null> {
  if (refreshing) return refreshing;
  const rt = session.refreshToken;
  if (!rt) return Promise.resolve(null);
  refreshing = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) {
        if (res.status === 401) setTokens(null);
        return null;
      }
      const t: TokenOut = await res.json();
      setTokens(t);
      return t.user;
    } catch {
      return null; // ağ hatası: oturumu silme, sonra tekrar denenebilir
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

export async function logout(): Promise<void> {
  const rt = session.refreshToken;
  setTokens(null);
  if (rt) {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
    }).catch(() => undefined);
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  form?: FormData;
  query?: Record<string, string | number | boolean | null | undefined>;
}

export async function api<T>(path: string, opts: RequestOptions = {}, retried = false): Promise<T> {
  if (!accessToken && session.refreshToken && !retried) {
    await refreshSession();
  }
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const tenant = session.tenantId;
  if (tenant) headers["X-Tenant-Id"] = tenant;
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const qs = opts.query
    ? "?" +
      new URLSearchParams(
        Object.entries(opts.query)
          .filter(([, v]) => v !== undefined && v !== null && v !== "")
          .map(([k, v]) => [k, String(v)]),
      ).toString()
    : "";

  const res = await send(`${API_BASE}${path}${qs === "?" ? "" : qs}`, {
    method: opts.method ?? "GET",
    headers,
    body,
  });

  if (res.status === 401 && !retried) {
    const user = await refreshSession();
    if (user) return api<T>(path, opts, true);
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Dosya indirme (ör. Excel şablonu): oturumla ister, tarayıcıya kaydettirir. */
export async function download(path: string, fallbackName: string): Promise<void> {
  if (!accessToken && session.refreshToken) await refreshSession();
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (session.tenantId) headers["X-Tenant-Id"] = session.tenantId;
  let res = await send(`${API_BASE}${path}`, { headers });
  if (res.status === 401 && (await refreshSession())) {
    headers.Authorization = `Bearer ${accessToken}`;
    res = await send(`${API_BASE}${path}`, { headers });
  }
  if (!res.ok) throw await parseError(res);
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/** Testler için: modül durumunu sıfırlar. */
export function __resetForTests() {
  accessToken = null;
  refreshing = null;
  listeners.clear();
}
