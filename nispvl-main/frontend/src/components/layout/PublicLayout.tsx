import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { Logo } from "../ui/ui";
import LangSwitch from "./LangSwitch";

export function PublicHeader() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const link = ({ isActive }: { isActive: boolean }) =>
    `hidden rounded-md px-2.5 py-1.5 text-sm font-medium no-underline md:inline-block ${isActive ? "text-field-800" : "text-ink-2 hover:text-ink"}`;
  return (
    <header className="sticky top-0 z-[1001] border-b border-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-2 px-4 sm:gap-4 sm:px-6">
        <Link to="/" className="no-underline">
          <span className="sm:hidden"><Logo compact /></span>
          <span className="hidden sm:inline"><Logo /></span>
        </Link>
        <nav className="ml-4 hidden items-center gap-1 md:flex" aria-label={t("nav.main")}>
          <NavLink to="/nasa" className={link}>{t("nav.nasa")}</NavLink>
          <NavLink to="/methodology" className={link}>{t("nav.methodology")}</NavLink>
          <NavLink to="/about" className={link}>{t("nav.about")}</NavLink>
        </nav>
        <div className="flex-1" />
        <LangSwitch />
        {user ? (
          <Link to="/app" className="btn-primary h-9 no-underline">{t("nav.dashboard")}</Link>
        ) : (
          <>
            <Link to="/login" className="btn-ghost hidden h-9 no-underline sm:inline-flex">{t("auth.login")}</Link>
            <Link to="/register" className="btn-primary h-9 no-underline">{t("auth.signup")}</Link>
          </>
        )}
      </div>
    </header>
  );
}

export function PublicFooter() {
  const { t } = useTranslation();
  return (
    <footer className="border-t border-line bg-white">
      <div className="mx-auto grid max-w-7xl gap-6 px-4 py-8 text-sm text-ink-muted sm:px-6 md:grid-cols-[1fr_auto]">
        <div className="space-y-2">
          <Logo />
          <p className="max-w-xl text-xs leading-relaxed">{t("app.disclaimer")}</p>
          <p className="max-w-xl text-xs leading-relaxed">{t("app.footer")}</p>
        </div>
        <nav className="flex flex-wrap items-start gap-x-5 gap-y-2" aria-label={t("nav.footer")}>
          <Link to="/nasa">{t("nav.nasa")}</Link>
          <Link to="/methodology">{t("nav.methodology")}</Link>
          <Link to="/retro">{t("nav.retro")}</Link>
          <Link to="/about">{t("nav.about")}</Link>
          <Link to="/quick">{t("nav.quick")}</Link>
        </nav>
      </div>
    </footer>
  );
}

export default function PublicLayout({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <PublicHeader />
      <main className={wide ? "flex-1" : "mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6"}>{children}</main>
      <PublicFooter />
    </div>
  );
}
