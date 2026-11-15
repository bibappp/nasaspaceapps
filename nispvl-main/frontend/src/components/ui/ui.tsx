import { AlertTriangle, CircleHelp, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { DataKind, RiskLevel } from "../../api/types";

export function Logo({ compact = false, light = false }: { compact?: boolean; light?: boolean }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-8 w-8 flex-none" aria-hidden>
        <rect width="32" height="32" rx="7" fill={light ? "#fff" : "#1F5134"} />
        <path d="M7 23h18M9 18.5h14M11 14h10" stroke={light ? "#1F5134" : "#fff"} strokeWidth="2.4" strokeLinecap="round" />
        <path d="M16 4.5c-2.6 2.4-2.6 5.6 0 7.3 2.6-1.7 2.6-4.9 0-7.3z" fill="#8DBF6A" />
      </svg>
      {!compact && <span className={`text-[15px] font-semibold tracking-tight ${light ? "text-white" : "text-ink"}`}>{t("app.name")}</span>}
    </span>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
        <h1 className="h1 truncate">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, icon, tone }: { label: ReactNode; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: "default" | "warn" | "bad" | "good" }) {
  const toneCls = tone === "bad" ? "text-status-bad" : tone === "warn" ? "text-status-warn" : tone === "good" ? "text-status-good" : "text-ink";
  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-ink-muted">
        {icon}
        <span>{label}</span>
      </div>
      <div className={`mt-1.5 text-xl font-semibold tabular-nums ${toneCls}`}>{value}</div>
      {hint && <div className="mt-1 text-xs leading-snug text-ink-muted">{hint}</div>}
    </div>
  );
}

export function Loading({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-ink-muted" role="status">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label ?? t("app.loading")}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900" role="alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" />
      <div className="flex-1">{message}</div>
      {onRetry && (
        <button type="button" className="btn-secondary h-8" onClick={onRetry}>
          {t("app.retry")}
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, text, action, icon }: { title: string; text?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line-strong bg-white px-6 py-12 text-center">
      <div className="mb-3 text-ink-subtle">{icon ?? <Inbox className="h-8 w-8" />}</div>
      <div className="h3">{title}</div>
      {text && <p className="mt-1 max-w-md text-sm text-ink-muted">{text}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Notice({ children, tone = "info", icon }: { children: ReactNode; tone?: "info" | "warn"; icon?: ReactNode }) {
  const cls = tone === "warn" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-line bg-surface-sunken text-ink-2";
  return (
    <div className={`flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-sm ${cls}`}>
      <span className="mt-0.5 flex-none">{icon ?? <CircleHelp className="h-4 w-4" />}</span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function LevelBadge({ level }: { level: RiskLevel }) {
  const { t } = useTranslation();
  const cls = level === "high" ? "badge-red" : level === "moderate" ? "badge-amber" : level === "low" ? "badge-green" : "badge-neutral";
  return <span className={cls}>{t(`risk.level.${level}`)}</span>;
}

/** Тип значения: наблюдение / реанализ / статистика / модель / допущение. */
export function KindBadge({ kind }: { kind: DataKind | "assumption" | "simulation" }) {
  const { t } = useTranslation();
  const cls =
    kind === "observation" ? "badge-blue" : kind === "model" || kind === "simulation" ? "badge-amber" : kind === "assumption" ? "badge-amber" : "badge-neutral";
  return <span className={cls} title={t(`kind.${kind}_hint`)}>{t(`kind.${kind}`)}</span>;
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; icon?: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="-mx-4 mb-6 overflow-x-auto border-b border-line px-4 sm:mx-0 sm:px-0" role="tablist">
      <div className="flex gap-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={value === tab.id}
            onClick={() => onChange(tab.id)}
            className={`-mb-px inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium ${
              value === tab.id ? "border-field-700 text-field-800" : "border-transparent text-ink-muted hover:text-ink"
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SectionTitle({ title, hint, actions }: { title: ReactNode; hint?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
      <div>
        <h2 className="h2">{title}</h2>
        {hint && <p className="mt-0.5 text-sm text-ink-muted">{hint}</p>}
      </div>
      {actions}
    </div>
  );
}
