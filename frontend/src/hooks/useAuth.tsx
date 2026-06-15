import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, setToken } from "../api/client";
import { can, type Permission } from "../api/rbac";
import type { Role } from "../types";

interface AuthState {
  username: string | null;
  role: Role | null;
  tenant: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string, tenant: string) => Promise<void>;
  logout: () => void;
  can: (permission: Permission) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [tenant, setTenant] = useState<string | null>(null);

  const login = useCallback(
    async (user: string, password: string, tenantName: string) => {
      const resp = await api.login(user, password, tenantName);
      setToken(resp.access_token);
      setUsername(user);
      setRole(resp.role);
      setTenant(resp.tenant);
    },
    [],
  );

  const logout = useCallback(() => {
    // Best-effort server-side revocation; clear local state regardless.
    void api.logout().catch(() => undefined);
    setToken(null);
    setUsername(null);
    setRole(null);
    setTenant(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      username,
      role,
      tenant,
      isAuthenticated: username !== null,
      login,
      logout,
      can: (permission: Permission) => can(role, permission),
    }),
    [username, role, tenant, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
