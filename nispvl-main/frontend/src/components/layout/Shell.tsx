import type { ReactNode } from "react";
import { useAuth } from "../../lib/auth";
import AppShell from "./AppShell";
import PublicLayout from "./PublicLayout";

/** Справочные страницы: внутри приложения для вошедших, в публичной обёртке для гостей. */
export default function Shell({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  return user ? <AppShell>{children}</AppShell> : <PublicLayout>{children}</PublicLayout>;
}
