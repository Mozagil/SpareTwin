import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { login as apiLogin, logout as apiLogout, refreshSession, session } from "../api/client";
import type { Me, Membership, Role } from "../api/types";

const ROLE_ORDER: Role[] = ["viewer", "technician", "manager", "admin", "owner"];

interface AuthState {
  status: "loading" | "anonymous" | "ready";
  user: Me | null;
  membership: Membership | null; // seçili firma
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  selectTenant: (tenantId: string) => void;
  can: (minimum: Role) => boolean;
}

const Ctx = createContext<AuthState | null>(null);

function pickMembership(user: Me | null): Membership | null {
  if (!user || user.memberships.length === 0) return null;
  if (user.memberships.length === 1) return user.memberships[0];
  const saved = session.tenantId;
  return user.memberships.find((m) => m.tenant_id === saved) ?? null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [user, setUser] = useState<Me | null>(null);
  const [membership, setMembership] = useState<Membership | null>(null);

  const apply = useCallback((u: Me | null) => {
    setUser(u);
    const m = pickMembership(u);
    setMembership(m);
    session.setTenant(m?.tenant_id ?? null);
    setStatus(u ? "ready" : "anonymous");
  }, []);

  useEffect(() => {
    // Oturum her değiştiğinde (giriş, yenileme, süre dolması) haberdar ol
    const unsub = session.subscribe((u) => {
      if (u) {
        setUser(u);
      } else {
        apply(null);
        qc.clear();
      }
    });
    refreshSession().then(apply);
    return () => {
      unsub();
    };
  }, [apply, qc]);

  const value = useMemo<AuthState>(
    () => ({
      status,
      user,
      membership,
      login: async (email, password) => {
        apply(await apiLogin(email, password));
      },
      logout: async () => {
        await apiLogout();
        qc.clear();
      },
      selectTenant: (tenantId) => {
        const m = user?.memberships.find((x) => x.tenant_id === tenantId) ?? null;
        session.setTenant(m?.tenant_id ?? null);
        setMembership(m);
        qc.clear();
      },
      can: (minimum) => !!membership && ROLE_ORDER.indexOf(membership.role) >= ROLE_ORDER.indexOf(minimum),
    }),
    [status, user, membership, apply, qc],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth, AuthProvider içinde kullanılmalı");
  return v;
}
