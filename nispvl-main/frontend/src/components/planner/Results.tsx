import { CheckCircle2, Info } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Comparison, Lang, ScoreWeights } from "../../api/types";
import { seriesColor } from "../../lib/colors";
import { useCropName } from "../../lib/config";
import { fmtInt, fmtNum, fmtSigned } from "../../lib/format";
import ForecastCharts from "../results/ForecastCharts";
import ScoreRow from "../results/ScoreRow";
import StressTest from "../results/StressTest";
import { variantName } from "../results/VariantCards";
import { KindBadge, SectionTitle } from "../ui/ui";
import { rank, SCORE_KEYS, type Ranked } from "./weights";

const LETTERS = "ABCDEF";

function CropChain({ crops }: { crops: string[] }) {
  const { i18n } = useTranslation();
  const cropName = useCropName();
  return <span className="text-xs text-ink-muted">{crops.map((c) => cropName(c, i18n.language as Lang)).join(" → ")}</span>;
}

function ReadingGuide() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border border-line bg-white px-3 py-2 text-xs text-ink-2">
      <span className="font-medium">{t("planner.guide")}</span>
      <span className="flex items-center gap-1.5"><KindBadge kind="observation" /> {t("planner.guide_obs")}</span>
      <span className="flex items-center gap-1.5"><KindBadge kind="assumption" /> {t("planner.guide_assumption")}</span>
      <span className="flex items-center gap-1.5"><KindBadge kind="simulation" /> {t("planner.guide_sim")}</span>
      <span>{t("planner.guide_no_forecast")}</span>
    </div>
  );
}

function Recommendation({ comparison, ranked, customWeights }: { comparison: Comparison; ranked: Ranked[]; customWeights: boolean }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const sorted = [...ranked].sort((a, b) => a.rank - b.rank);
  const best = sorted[0];
  const second = sorted[1];
  if (!best) return null;
  const v = best.v;
  const conf = v.confidence;
  const basis = comparison.conditions.moisture_basis;
  const drivers = second
    ? SCORE_KEYS.map((k) => ({ k, d: best.contributions[k] - second.contributions[k] })).sort((a, b) => b.d - a.d)
    : [];
  const margin = second ? best.weighted - second.weighted : null;
  return (
    <section className="panel overflow-hidden">
      <div className="border-b border-line bg-field-50 px-5 py-4">
        <div className="eyebrow text-field-800">{t("planner.recommended")}</div>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded text-sm font-semibold text-white" style={{ background: seriesColor(best.index) }}>{LETTERS[best.index]}</span>
          <h2 className="text-xl font-semibold text-ink">{variantName(v, lang, t)}</h2>
          <span className="text-sm text-ink-muted">{t("planner.weighted", { score: fmtNum(best.weighted, 2) })}</span>
        </div>
        <div className="mt-1"><CropChain crops={v.crops} /></div>
      </div>
      <div className="grid gap-6 p-5 lg:grid-cols-3">
        <div className="space-y-2 lg:col-span-2">
          <h3 className="h3">{t("planner.why")}</h3>
          {second && margin !== null && (
            <p className="text-sm text-ink-2">
              {t("planner.why_margin", { second: variantName(second.v, lang, t), margin: fmtNum(margin, 2) })}{" "}
              {margin < 0.15 && <b>{t("planner.close_call")}</b>}
            </p>
          )}
          {drivers.length > 0 && (
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {drivers.map(({ k, d }) => (
                <li key={k} className="flex items-center justify-between rounded border border-line px-2.5 py-1.5 text-sm">
                  <span>{t(`result.scores.${k}`)} · {fmtNum(v.scores[k].score, 1)}/5</span>
                  <span className={`tabular-nums ${d > 0 ? "text-status-good" : d < 0 ? "text-status-bad" : "text-ink-muted"}`}>{d > 0 ? "+" : ""}{fmtNum(d, 2)}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="hint">{t("planner.drivers_hint")}</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-2">
            {v.explanation.map((e, i) => (
              <li key={`${e.code}-${i}`} className={e.code === "assumptions" ? "text-amber-900" : ""}>{e[lang]}</li>
            ))}
          </ul>
        </div>
        <div className="space-y-4 text-sm">
          <div>
            <h3 className="h3 mb-1">{t("planner.confidence")}</h3>
            <span className={conf.level === "high" ? "badge-green" : conf.level === "medium" ? "badge-amber" : "badge-red"}>{t(`planner.conf.${conf.level}`)}</span>
            <p className="mt-1 text-xs text-ink-muted">{t("planner.confidence_detail", { supported: conf.params_supported, total: conf.params_total, pct: fmtNum(conf.share * 100, 0) })}</p>
          </div>
          <div>
            <h3 className="h3 mb-1">{t("planner.conditions")}</h3>
            <ul className="space-y-0.5 text-xs text-ink-2">
              <li>{t("planner.cond_weights", { kind: customWeights ? t("planner.custom") : comparison.priority_name[lang] })}</li>
              <li>{t("planner.cond_water", { normal: fmtInt(comparison.normal_water_mm), dry: fmtInt(comparison.dry_water_mm), year: comparison.conditions.dry_year })}</li>
              <li>{t("planner.cond_horizon", { from: comparison.start_year, to: comparison.start_year + comparison.horizon_years - 1 })}</li>
            </ul>
          </div>
          <div>
            <h3 className="h3 mb-1">{t("planner.datasets")}</h3>
            <ul className="space-y-0.5 text-xs text-ink-2">
              <li>NASA POWER — {t("planner.ds_power")}</li>
              <li>{basis === "smap" ? `SMAP — ${t("planner.ds_smap")}` : `NASA POWER GWETROOT — ${t("planner.ds_gwet")}`}</li>
              {comparison.conditions.awc_mm !== null && <li>ISRIC SoilGrids — {t("planner.ds_soil")}</li>}
              <li className="text-ink-muted">{t("planner.ds_modis_not_used")}</li>
            </ul>
          </div>
        </div>
      </div>
      <div className="border-t border-line bg-surface px-5 py-3 text-xs leading-relaxed text-ink-muted">
        <b className="text-ink-2">{t("planner.limitations")}:</b> {t("planner.limitations_text")}
      </div>
    </section>
  );
}

function ComparisonTable({ comparison, ranked }: { comparison: Comparison; ranked: Ranked[] }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const base = comparison.variants.find((x) => x.id === comparison.baseline_variant_id);
  const years = t("wizard.history.years", { count: comparison.horizon_years });
  const row = (label: string, cells: (r: Ranked) => React.ReactNode, opts: { hint?: string; kind?: "simulation" | "assumption" } = {}) => (
    <tr key={label}>
      <th scope="row" className="whitespace-normal bg-surface/60 text-left font-normal text-ink-2">
        <div className="flex items-center gap-1.5">{label} {opts.kind && <KindBadge kind={opts.kind} />}</div>
        {opts.hint && <div className="text-xs text-ink-muted">{opts.hint}</div>}
      </th>
      {ranked.map((r) => <td key={r.v.id} className="num">{cells(r)}</td>)}
    </tr>
  );
  const kzt = (v: number) => `${fmtInt(v)}`;
  return (
    <div className="panel overflow-x-auto">
      <table className="table min-w-[760px]">
        <thead>
          <tr>
            <th className="w-56">{t("planner.metric")}</th>
            {ranked.map((r) => (
              <th key={r.v.id} className="text-right align-bottom">
                <div className="flex items-center justify-end gap-1.5">
                  {r.rank === 1 && <CheckCircle2 className="h-4 w-4 text-field-700" aria-label={t("planner.recommended")} />}
                  <span className="inline-flex h-5 w-5 items-center justify-center rounded text-[11px] font-semibold text-white" style={{ background: seriesColor(r.index) }}>{LETTERS[r.index]}</span>
                </div>
                <div className="mt-1 whitespace-normal font-medium normal-case text-ink">{variantName(r.v, lang, t)}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {row(t("planner.rank"), (r) => <span className={r.rank === 1 ? "font-semibold text-field-800" : ""}>{r.rank}</span>)}
          {row(t("planner.weighted_score"), (r) => <b>{fmtNum(r.weighted, 2)}</b>, { hint: t("planner.weighted_hint") })}
          {SCORE_KEYS.map((k) => row(t(`result.scores.${k}`), (r) => `${fmtNum(r.v.scores[k].score, 1)} / 5`))}
          <tr><td colSpan={ranked.length + 1} className="bg-surface pt-4 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("planner.economics", { years })}</td></tr>
          {row(t("planner.revenue"), (r) => kzt(r.v.economics.revenue_kzt_ha), { hint: t("units.kzt_ha"), kind: "simulation" })}
          {row(t("planner.costs"), (r) => kzt(r.v.economics.cost_kzt_ha), { hint: t("units.kzt_ha"), kind: "assumption" })}
          {row(t("planner.gross_margin"), (r) => <b>{kzt(r.v.economics.gross_margin_kzt_ha)}</b>, { hint: t("planner.gross_margin_hint") })}
          {row(t("planner.vs_baseline"), (r) => (base && base.id !== r.v.id ? fmtSigned(r.v.economics.gross_margin_kzt_ha - base.economics.gross_margin_kzt_ha) : "—"))}
          {row(t("planner.field_total"), (r) => fmtInt(r.v.totals.income_field_kzt), { hint: t("planner.field_total_hint", { area: fmtNum(comparison.conditions.area_ha, 1) }) })}
          {row(t("planner.price_minus"), (r) => kzt(r.v.economics.margin_price_minus20_kzt_ha), { hint: t("planner.price_hint") })}
          {row(t("planner.price_plus"), (r) => kzt(r.v.economics.margin_price_plus20_kzt_ha))}
          {row(t("planner.breakeven"), (r) => (r.v.economics.breakeven_price_factor === null ? "—" : `${fmtNum(r.v.economics.breakeven_price_factor * 100, 0)} %`), { hint: t("planner.breakeven_hint") })}
          <tr><td colSpan={ranked.length + 1} className="bg-surface pt-4 text-xs font-semibold uppercase tracking-wider text-ink-muted">{t("planner.soil_water_risk")}</td></tr>
          {row(t("planner.soil_change"), (r) => fmtNum(r.v.totals.soil_index_change, 1), { hint: t("planner.soil_change_hint"), kind: "simulation" })}
          {row(t("planner.nitrogen"), (r) => fmtNum(r.v.totals.nitrogen_kg_ha, 0), { hint: t("units.kg_ha") })}
          {row(t("planner.humus"), (r) => fmtNum(r.v.totals.humus_t_ha, 2), { hint: t("units.t_ha") })}
          {row(t("planner.water_deficit"), (r) => fmtNum(r.v.totals.water_deficit_mean_mm, 0), { hint: t("units.mm") })}
          {row(t("planner.drought_loss"), (r) => `${fmtNum(r.v.totals.drought_loss_pct, 1)} %`, { hint: t("planner.drought_loss_hint", { year: comparison.conditions.dry_year }) })}
          {row(t("planner.monoculture"), (r) => r.v.totals.monoculture_years)}
          {row(t("planner.confidence"), (r) => t(`planner.conf.${r.v.confidence.level}`))}
          {row(t("planner.assumptions"), (r) => `${r.v.assumptions_used} / ${r.v.params_used}`, { hint: t("planner.assumptions_hint") })}
        </tbody>
      </table>
    </div>
  );
}

function ScoreDetails({ comparison }: { comparison: Comparison }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {comparison.variants.map((v, i) => (
        <div key={v.id} className="panel p-4" style={{ borderTop: `3px solid ${seriesColor(i)}` }}>
          <div className="mb-3">
            <div className="text-sm font-semibold">{LETTERS[i]}. {variantName(v, lang, t)}</div>
            <CropChain crops={v.crops} />
          </div>
          <div className="space-y-2.5">
            {SCORE_KEYS.map((k) => <ScoreRow key={k} k={k} score={v.scores[k]} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Results({ comparison, weights, customWeights }: { comparison: Comparison; weights: ScoreWeights; customWeights: boolean }) {
  const { t } = useTranslation();
  const ranked = useMemo(() => rank(comparison, weights), [comparison, weights]);
  const [stressIdx, setStressIdx] = useState<number | null>(null);
  return (
    <div className="space-y-8">
      <ReadingGuide />
      <Recommendation comparison={comparison} ranked={ranked} customWeights={customWeights} />
      <section>
        <SectionTitle title={t("planner.compare_title")} hint={t("planner.compare_hint")} />
        <ComparisonTable comparison={comparison} ranked={ranked} />
      </section>
      <section>
        <SectionTitle title={t("planner.scores_title")} hint={t("planner.scores_hint")} />
        <ScoreDetails comparison={comparison} />
      </section>
      <section>
        <SectionTitle title={t("planner.simulation_title")} hint={t("planner.simulation_hint")} />
        <ForecastCharts comparison={comparison} />
      </section>
      <section>
        <SectionTitle title={t("planner.drought_title")} hint={t("planner.drought_hint", { year: comparison.conditions.dry_year })} />
        <StressTest comparison={comparison} yearIndex={stressIdx} onYearIndex={setStressIdx} />
      </section>
      <p className="flex items-start gap-2 text-xs text-ink-muted"><Info className="mt-0.5 h-3.5 w-3.5 flex-none" /> {t("app.disclaimer")}</p>
    </div>
  );
}
