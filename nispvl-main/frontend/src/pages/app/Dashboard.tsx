import { AlertTriangle, ArrowRight, FileBarChart, Map as MapIcon, Plus, Scale } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { FieldRecord, Lang, Risk, RiskLevel } from "../../api/types";
import TelegramBotCard from "../../components/common/TelegramBotCard";
import FieldThumb from "../../components/fields/FieldThumb";
import { RiskGrid, useRiskText } from "../../components/workspace/RiskCards";
import { EmptyState, ErrorBox, LevelBadge, Loading, Notice, PageHeader, SectionTitle, Stat } from "../../components/ui/ui";
import { errorText, fmtDate, useAsync } from "../../lib/async";
import { useAuth } from "../../lib/auth";
import { useConfig, useCropName } from "../../lib/config";
import { fmtInt, fmtNum } from "../../lib/format";
import { tx } from "../../lib/i18n-text";

/** Риск по каждому полю грузится отдельно: одно медленное поле не задерживает остальные. */
function useFieldRisks(fields: FieldRecord[] | undefined) {
  const [risks, setRisks] = useState<Record<number, Risk | "error">>({});
  useEffect(() => {
    if (!fields) return;
    let alive = true;
    fields.forEach((f) => {
      api
        .fieldRisk(f.id)
        .then((r) => alive && setRisks((s) => ({ ...s, [f.id]: r })))
        .catch(() => alive && setRisks((s) => ({ ...s, [f.id]: "error" })));
    });
    return () => {
      alive = false;
    };
  }, [fields]);
  return risks;
}

export default function Dashboard() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { user } = useAuth();
  const { config } = useConfig();
  const cropName = useCropName();
  const riskText = useRiskText();
  const fields = useAsync(() => api.fields().then((r) => r.fields), []);
  const analyses = useAsync(() => api.recentAnalyses(6).then((r) => r.analyses), []);
  const risks = useFieldRisks(fields.data ?? undefined);
  const [selected, setSelected] = useState<number | null>(null);

  const list = fields.data ?? [];
  const focusId = selected ?? list[0]?.id ?? null;
  const focus = list.find((f) => f.id === focusId);
  const focusRisk = focusId != null ? risks[focusId] : undefined;
  const totalArea = list.reduce((s, f) => s + f.area_ha, 0);
  const nAnalyses = list.reduce((s, f) => s + (f.n_analyses ?? 0), 0);
  const warnings = list.flatMap((f) => {
    const r = risks[f.id];
    if (!r || r === "error") return [];
    return r.items.filter((i) => i.level === "high" && i.id !== "model_drought_exposure").map((i) => ({ field: f, item: i }));
  });
  const regionName = (id: string) => tx(config?.regions.find((r) => r.id === id)?.name, lang) || id;
  const greeting = user?.is_demo ? t("dashboard.greeting_demo") : t("dashboard.greeting", { name: user?.name || user?.email });

  return (
    <div className="space-y-8">
      <PageHeader
        title={greeting}
        subtitle={user?.farm_name || t("dashboard.subtitle")}
        actions={
          <>
            <Link to="/app/fields/new" className="btn-secondary no-underline">
              <Plus className="h-4 w-4" /> {t("fields.add")}
            </Link>
            {focus && (
              <Link to={`/app/fields/${focus.id}?tab=planner`} className="btn-primary no-underline">
                <Scale className="h-4 w-4" /> {t("dashboard.open_planner")}
              </Link>
            )}
          </>
        }
      />

      <TelegramBotCard />

      {fields.error ? <ErrorBox message={errorText(fields.error, t)} onRetry={fields.reload} /> : null}
      {fields.loading && !fields.data && <Loading />}

      {fields.data && list.length === 0 && (
        <EmptyState
          icon={<MapIcon className="h-8 w-8" />}
          title={t("dashboard.empty_title")}
          text={t("dashboard.empty_text")}
          action={
            <Link to="/app/fields/new" className="btn-primary no-underline">
              <Plus className="h-4 w-4" /> {t("fields.add")}
            </Link>
          }
        />
      )}

      {list.length > 0 && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label={t("dashboard.stat_fields")} value={list.length} />
            <Stat label={t("dashboard.stat_area")} value={`${fmtInt(totalArea)} ${t("units.ha")}`} />
            <Stat label={t("dashboard.stat_analyses")} value={nAnalyses} />
            <Stat
              label={t("dashboard.stat_warnings")}
              value={warnings.length}
              tone={warnings.length ? "warn" : "default"}
              hint={t("dashboard.stat_warnings_hint")}
            />
          </div>

          <section>
            <SectionTitle
              title={t("dashboard.fields_title")}
              actions={<Link to="/app/fields" className="text-sm">{t("dashboard.all_fields")} <ArrowRight className="inline h-3.5 w-3.5" /></Link>}
            />
            <div className="panel overflow-x-auto">
              <table className="table min-w-[720px]">
                <thead>
                  <tr>
                    <th>{t("fields.col_name")}</th>
                    <th>{t("fields.col_region")}</th>
                    <th className="num">{t("fields.col_area")}</th>
                    <th>{t("fields.col_last_crop")}</th>
                    <th>{t("dashboard.col_risk")}</th>
                    <th>{t("fields.col_last_analysis")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {list.map((f) => {
                    const r = risks[f.id];
                    const last = f.history[f.history.length - 1];
                    return (
                      <tr key={f.id} className={f.id === focusId ? "bg-field-50/60" : ""}>
                        <td>
                          <button type="button" className="flex items-center gap-3 text-left" onClick={() => setSelected(f.id)}>
                            <FieldThumb geometry={f.geometry} size={34} />
                            <span className="font-medium text-ink">{f.name}</span>
                          </button>
                        </td>
                        <td className="text-ink-2">{regionName(f.region)}</td>
                        <td className="num">{fmtNum(f.area_ha, 1)}</td>
                        <td>{last ? `${cropName(last.crop, lang)} · ${last.year}` : "—"}</td>
                        <td>{r === undefined ? <span className="text-xs text-ink-subtle">{t("app.loading")}</span> : r === "error" ? <span className="text-xs text-ink-subtle">{t("risk.unavailable")}</span> : <LevelBadge level={r.overall as RiskLevel} />}</td>
                        <td className="text-ink-2">{f.last_analysis_at ? fmtDate(f.last_analysis_at, lang) : "—"}</td>
                        <td className="text-right">
                          <Link to={`/app/fields/${f.id}`} className="btn-ghost h-8 no-underline">
                            {t("fields.open")} <ArrowRight className="h-3.5 w-3.5" />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <div className="grid gap-8 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <section>
              <SectionTitle
                title={t("dashboard.indicators_title", { field: focus?.name ?? "" })}
                hint={focusRisk && focusRisk !== "error" ? t("dashboard.indicators_hint", { season: focusRisk.latest_season }) : undefined}
                actions={
                  list.length > 1 ? (
                    <select className="input h-9 w-auto" value={focusId ?? ""} onChange={(e) => setSelected(Number(e.target.value))} aria-label={t("dashboard.select_field")}>
                      {list.map((f) => (
                        <option key={f.id} value={f.id}>{f.name}</option>
                      ))}
                    </select>
                  ) : null
                }
              />
              {focusRisk === undefined && <Loading />}
              {focusRisk === "error" && <ErrorBox message={t("risk.unavailable")} />}
              {focusRisk && focusRisk !== "error" && <RiskGrid risk={focusRisk} compact />}
              {focus && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link to={`/app/fields/${focus.id}?tab=monitoring`} className="btn-secondary h-8 no-underline">{t("tabs.monitoring")}</Link>
                  <Link to={`/app/fields/${focus.id}?tab=history`} className="btn-secondary h-8 no-underline">{t("tabs.history")}</Link>
                  <Link to={`/app/fields/${focus.id}?tab=risk`} className="btn-secondary h-8 no-underline">{t("tabs.risk")}</Link>
                </div>
              )}
            </section>

            <div className="space-y-8">
              <section>
                <SectionTitle title={t("dashboard.warnings_title")} />
                {warnings.length === 0 ? (
                  <Notice>{Object.keys(risks).length < list.length ? t("app.loading") : t("dashboard.no_warnings")}</Notice>
                ) : (
                  <ul className="space-y-2">
                    {warnings.map(({ field, item }) => (
                      <li key={`${field.id}-${item.id}`} className="flex items-start gap-2.5 rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-950">
                        <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" />
                        <div className="min-w-0">
                          <div className="font-medium">
                            {field.name}: {t(`risk.item.${item.id}`)} — {riskText(item).value}
                          </div>
                          <div className="text-xs text-amber-900/80">{riskText(item).detail}</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section>
                <SectionTitle
                  title={t("dashboard.recent_title")}
                  actions={<Link to="/app/analyses" className="text-sm">{t("dashboard.all_analyses")}</Link>}
                />
                {analyses.loading && !analyses.data && <Loading />}
                {analyses.data?.length === 0 && <Notice>{t("dashboard.no_analyses")}</Notice>}
                <ul className="divide-y divide-line rounded-lg border border-line bg-white">
                  {(analyses.data ?? []).map((a) => (
                    <li key={a.id}>
                      <Link to={`/app/analyses/${a.id}`} className="flex items-center gap-3 px-4 py-3 no-underline hover:bg-surface">
                        <FileBarChart className="h-4 w-4 flex-none text-ink-muted" />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-ink">{a.title || a.field_name}</div>
                          <div className="truncate text-xs text-ink-muted">
                            {a.field_name} · {fmtDate(a.created_at, lang)} · {t("dashboard.best")}: {a.summary.best_crops.map((c) => cropName(c, lang)).join(" → ")}
                          </div>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
