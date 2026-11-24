"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { apiRequest, onSessionExpired, refreshSession, setAccessToken } from "@/lib/api-client";
import type { AdminMe, Permission, TokenOut } from "@/types/api";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthState {
  status: Status;
  admin: AdminMe | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: Permission) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [admin, setAdmin] = useState<AdminMe | null>(null);
  const router = useRouter();

  // Restore the session from the HttpOnly refresh cookie on first load.
  useEffect(() => {
    let cancelled = false;
    refreshSession().then((data) => {
      if (cancelled) return;
      if (data) {
        setAdmin(data.admin as AdminMe);
        setStatus("authenticated");
      } else {
        setStatus("anonymous");
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(
    () =>
      onSessionExpired(() => {
        setAccessToken(null);
        setAdmin(null);
        setStatus("anonymous");
      }),
    [],
  );

  const login = useCallback(async (email: string, password: string) => {
    const data = await apiRequest<TokenOut>("/admin/auth/login", {
      method: "POST",
      body: { email, password },
      anonymous: true,
    });
    setAccessToken(data.access_token);
    setAdmin(data.admin);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiRequest("/admin/auth/logout", { method: "POST", anonymous: true });
    } finally {
      setAccessToken(null);
      setAdmin(null);
      setStatus("anonymous");
      router.replace("/login");
    }
  }, [router]);

  const can = useCallback(
    (permission: Permission) => admin?.permissions.includes(permission) ?? false,
    [admin],
  );

  const value = useMemo(
    () => ({ status, admin, login, logout, can }),
    [status, admin, login, logout, can],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
