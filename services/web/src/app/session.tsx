/**
 * Who is signed in, and which workspace they are acting in.
 *
 * The access token is deliberately not in this state and not in storage: it lives inside
 * the API client's module scope, which React cannot serialize into a devtools dump and a
 * script cannot read out of `localStorage`. What lives here is only what the UI renders.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, setAccessToken, setTenant } from "@/api/client";
import type { Tenant, User } from "@/api/types";
import { LAST_TENANT_KEY, SessionContext, type Session } from "@/app/session-context";

interface TokenPair {
  access: string;
  expires_in: number;
  user: User;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [tenant, setTenantState] = useState<Tenant | null>(null);
  const [ready, setReady] = useState(false);

  const chooseTenant = useCallback((next: Tenant | null) => {
    setTenantState(next);
    setTenant(next?.slug ?? null);
    if (next) localStorage.setItem(LAST_TENANT_KEY, next.slug);
    else localStorage.removeItem(LAST_TENANT_KEY);
  }, []);

  // On load, try the refresh cookie. It is the only credential that survives a reload,
  // which is what makes a memory-only access token workable.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const pair = await api.post<TokenPair>("/v1/auth/refresh/");
        if (cancelled) return;
        setAccessToken(pair.access);
        setUser(pair.user);

        const remembered = localStorage.getItem(LAST_TENANT_KEY);
        if (remembered) setTenant(remembered);
      } catch {
        // No session. Not an error: this is what a first visit looks like.
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const pair = await api.post<TokenPair>("/v1/auth/login/", { email, password });
    setAccessToken(pair.access);
    setUser(pair.user);
  }, []);

  const signOut = useCallback(async () => {
    await api.post("/v1/auth/logout/");
    setAccessToken(null);
    setUser(null);
    setTenantState(null);
    setTenant(null);
    localStorage.removeItem(LAST_TENANT_KEY);
  }, []);

  const value = useMemo<Session>(
    () => ({ user, tenant, ready, signIn, signOut, chooseTenant }),
    [user, tenant, ready, signIn, signOut, chooseTenant],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
