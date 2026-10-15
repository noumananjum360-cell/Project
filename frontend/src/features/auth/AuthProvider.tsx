import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, setCsrfToken, setUnauthorizedHandler } from "@/lib/api";
import { authApi } from "@/services";
import type { User } from "@/types/api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (email: string, password: string, fullName?: string) => Promise<User>;
  logout: () => Promise<void>;
  setUser: (u: User | null) => void;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  useEffect(() => {
    let active = true;
    authApi
      .session()
      .then((r) => {
        if (!active) return;
        setCsrfToken(r.csrf_token);
        setUser(r.user);
      })
      .catch((e) => {
        if (active && !(e instanceof ApiError && e.status === 401)) console.warn("Session check failed");
      })
      .finally(() => active && setLoading(false));
    setUnauthorizedHandler(() => {
      setUser(null);
      qc.clear();
    });
    return () => {
      active = false;
      setUnauthorizedHandler(null);
    };
  }, [qc]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await authApi.login(email, password);
    setCsrfToken(r.csrf_token);
    setUser(r.user);
    return r.user;
  }, []);

  const register = useCallback(async (email: string, password: string, fullName?: string) => {
    const r = await authApi.register(email, password, fullName);
    setCsrfToken(r.csrf_token);
    setUser(r.user);
    return r.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setCsrfToken(null);
      setUser(null);
      qc.clear();
    }
  }, [qc]);

  const value = useMemo(() => ({ user, loading, login, register, logout, setUser }), [user, loading, login, register, logout]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
