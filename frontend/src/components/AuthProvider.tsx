"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, UNAUTHORIZED_EVENT } from "@/lib/api";
import { clearSession, getExpiresAt, getToken, saveSession } from "@/lib/session";
import type { User } from "@/lib/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: (reason?: "expired") => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(
    (reason?: "expired") => {
      clearSession();
      setUser(null);
      router.replace(reason === "expired" ? "/login?expired=1" : "/login");
    },
    [router],
  );

  const refreshUser = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    try {
      setUser(await api.me());
    } catch {
      setUser(null);
    }
  }, []);

  // Restore the session on first load.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = getToken();
      const current = token ? await api.me().catch(() => null) : null;
      if (!cancelled) {
        setUser(current);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Any API call that gets a 401 (expired/invalid token) logs the user out.
  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null);
      router.replace("/login?expired=1");
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [router]);

  // Log out automatically when the token reaches its expiry time.
  useEffect(() => {
    if (!user) return;
    const remaining = Math.max(getExpiresAt() - Date.now(), 0);
    const timer = window.setTimeout(() => logout("expired"), Math.min(remaining, 2_147_000_000));
    return () => window.clearTimeout(timer);
  }, [user, logout]);

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login({ email, password });
    saveSession(result.access_token, result.expires_in);
    setUser(result.user);
  }, []);

  const register = useCallback(
    async (name: string, email: string, password: string) => {
      await api.register({ name, email, password });
      await login(email, password);
    },
    [login],
  );

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refreshUser }),
    [user, loading, login, register, logout, refreshUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
