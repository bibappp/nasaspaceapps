import { BookOpen, FileBarChart, FlaskConical, LayoutDashboard, LogOut, Map as MapIcon, Menu, Satellite, Settings, X, Zap } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { Logo } from "../ui/ui";
import LangSwitch from "./LangSwitch";

const NAV = [
  { to: "/app", icon: LayoutDashboard, key: "dashboard", end: true },
  { to: "/app/fields", icon: MapIcon, key: "fields" },
  { to: "/app/analyses", icon: FileBarChart, key: "analyses" },
];
const NAV_INFO = [
  { to: "/nasa", icon: Satellite, key: "nasa" },
  { to: "/methodology", icon: BookOpen, key: "methodology" },
  { to: "/retro", icon: FlaskConical, key: "retro" },
  { to: "/quick", icon: Zap, key: "quick" },
];

function NavItem({ to, icon: Icon, label, end }: { to: string; icon: typeof MapIcon; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium no-underline ${
          isActive ? "bg-field-50 text-field-800" : "text-ink-2 hover:bg-surface-sunken hover:text-ink"
        }`
      }
    >
      <Icon className="h-4 w-4 flex-none" />
      {label}
    </NavLink>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="flex h-full flex-col" onClick={(e) => (e.target as HTMLElement).closest("a") && onNavigate?.()}>
      <div className="flex h-14 items-center border-b border-line px-4">
        <Link to="/app" className="no-underline">
          <Logo />
        </Link>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4" aria-label={t("nav.main")}>
        <div className="space-y-0.5">
          {NAV.map((n) => (
            <NavItem key={n.to} to={n.to} icon={n.icon} end={n.end} label={t(`nav.${n.key}`)} />
          ))}
        </div>
        <div>
          <div className="eyebrow mb-1.5 px-2.5">{t("nav.reference")}</div>
          <div className="space-y-0.5">
            {NAV_INFO.map((n) => (
              <NavItem key={n.to} to={n.to} icon={n.icon} label={t(`nav.${n.key}`)} />
            ))}
          </div>
        </div>
      </nav>
      {user && (
        <div className="border-t border-line p-3">
          <div className="mb-2 min-w-0 px-1">
            <div className="truncate text-sm font-medium text-ink">{user.is_demo ? t("auth.demo_user") : user.name || user.email}</div>
            <div className="truncate text-xs text-ink-muted">{user.is_demo ? t("auth.demo_user_hint") : user.farm_name || user.email}</div>
          </div>
          <div className="flex gap-1">
            {!user.is_demo && (
              <NavLink to="/app/account" className="btn-ghost h-8 flex-1 justify-start px-2 text-xs no-underline">
                <Settings className="h-3.5 w-3.5" /> {t("nav.account")}
              </NavLink>
            )}
            <button
              type="button"
              className="btn-ghost h-8 flex-1 justify-start px-2 text-xs"
              onClick={() => void logout().then(() => navigate("/"))}
            >
              <LogOut className="h-3.5 w-3.5" /> {t("auth.logout")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  return (
    <div className="min-h-screen bg-surface">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-line bg-white lg:block">
        <Sidebar />
      </aside>
      {open && (
        <div className="fixed inset-0 z-[1100] lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-ink/30" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-white shadow-lg">
            <button type="button" className="btn-icon absolute right-2 top-3" aria-label={t("app.close")} onClick={() => setOpen(false)}>
              <X className="h-4 w-4" />
            </button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-white/95 px-4 backdrop-blur sm:px-6">
          <button type="button" className="btn-icon lg:hidden" aria-label={t("nav.menu")} onClick={() => setOpen(true)}>
            <Menu className="h-4 w-4" />
          </button>
          <div className="lg:hidden">
            <Logo compact />
          </div>
          <div className="flex-1" />
          <LangSwitch />
        </header>
        {user?.is_demo && (
          <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900 sm:px-6">
            {t("auth.demo_banner")}{" "}
            <Link to="/register" className="font-semibold text-amber-900">
              {t("auth.demo_banner_cta")}
            </Link>
          </div>
        )}
        <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:py-8">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-ink-muted sm:px-6">{t("app.disclaimer")}</footer>
      </div>
    </div>
  );
}
