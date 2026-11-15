import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Lang, User } from "../api/types";
import { Loading } from "../components/ui/ui";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (body: { email: string; password: string; name: string; farm_name: string; lang: Lang }) => Promise<User>;
  demo: () => Promise<User>;
  logout: () => Promise<void>;
  setUser: (u: User) => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch((e: ApiError) => {
        if (e.status !== 401) console.warn("auth check failed", e.detail);
      })
      .finally(() => setLoading(false));
  }, []);

  const apply = useCallback(
    (u: User) => {
      setUser(u);
      if (u.lang && u.lang !== i18n.language && !u.is_demo) void i18n.changeLanguage(u.lang);
      return u;
    },
    [i18n],
  );

  const value: AuthState = {
    user,
    loading,
    login: async (email, password) => apply(await api.login(email, password)),
    register: async (body) => apply(await api.register(body)),
    demo: async () => apply(await api.demoLogin(i18n.language as Lang)),
    logout: async () => {
      await api.logout().catch(() => undefined);
      setUser(null);
    },
    setUser: apply,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}
