import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import LangSwitch from "../../components/layout/LangSwitch";
import { Logo } from "../../components/ui/ui";

export default function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="grid min-h-screen bg-surface lg:grid-cols-[1fr_minmax(0,520px)]">
      <div className="relative hidden flex-col justify-between bg-field-800 p-10 text-white lg:flex">
        <Link to="/" className="no-underline">
          <Logo light />
        </Link>
        <div className="max-w-md space-y-4">
          <p className="text-xl font-semibold leading-snug">{t("auth.side_title")}</p>
          <ul className="space-y-2 text-sm text-white/80">
            <li>— {t("auth.side_1")}</li>
            <li>— {t("auth.side_2")}</li>
            <li>— {t("auth.side_3")}</li>
          </ul>
        </div>
        <p className="text-xs text-white/60">{t("app.disclaimer")}</p>
      </div>
      <div className="flex flex-col">
        <div className="flex h-14 items-center justify-between px-6">
          <Link to="/" className="no-underline lg:invisible">
            <Logo />
          </Link>
          <LangSwitch />
        </div>
        <div className="flex flex-1 items-center justify-center px-6 pb-12">
          <div className="w-full max-w-sm">
            <h1 className="h1">{title}</h1>
            {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
            <div className="mt-6">{children}</div>
            {footer && <div className="mt-6 text-sm text-ink-muted">{footer}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
