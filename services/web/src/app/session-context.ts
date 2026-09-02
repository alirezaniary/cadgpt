/**
 * The session context and its hook, kept apart from the provider component.
 *
 * Not a stylistic split: a module that exports both a component and a plain value cannot
 * be hot-reloaded as a component, so the provider would remount -- and drop the signed-in
 * session -- on every edit during development.
 */

import { createContext, useContext } from "react";

import type { Tenant, User } from "@/api/types";

export interface Session {
  user: User | null;
  tenant: Tenant | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  chooseTenant: (tenant: Tenant | null) => void;
}

export const SessionContext = createContext<Session | null>(null);

/** Where the chosen workspace is remembered between visits. */
export const LAST_TENANT_KEY = "tenant";

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside a SessionProvider");
  return session;
}
