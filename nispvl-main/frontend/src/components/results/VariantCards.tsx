import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Comparison, Lang, ScoreKey, Variant, VariantResult } from "../../api/types";
import { seriesColor } from "../../lib/colors";
import { useConfig, useCropName } from "../../lib/config";
import { fmtInt, fmtNum, fmtSigned } from "../../lib/format";
import ScoreRow from "./ScoreRow";

const KEYS: ScoreKey[] = ["soil", "water", "income", "risk"];

export function variantName(v: { id: string; name?: Variant["name"]; custom?: boolean }, lang: Lang, t: (k: string) => string): string {
  if (v.name) return v.name[lang];
  return v.custom ? t("result.compare.custom_name") : v.id;
}

function Card({ v, index, comparison, lang }: { v: VariantResult; index: number; comparison: Comparison; lang: Lang }) {
  const { t } = useTranslation();
  const cropName = useCropName();
  const base = comparison.variants.find((x) => x.id === comparison.baseline_variant_id);
  const diff = base && base.id !== v.id ? v.totals.income_kzt_ha - base.totals.income_kzt_ha : null;
  const years = t("wizard.history.years", { count: comparison.horizon_years });
  return (
    <article
      className={`card flex flex-col gap-3 border-t-4 ${v.fits_priority ? "ring-2 ring-field-300" : ""}`}
      style={{ borderTopColor: seriesColor(index) }}
    >
      {v.fits_priority && (
        <div className="-mx-1 flex items-center gap-1.5 rounded-md bg-field-50 px-2.5 py-1.5 text-sm font-medium text-field-800"><CheckCircle2 className="h-4 w-4" /> {t("result.compare.fits")}</div>
      )}
      <h3 className="h3">
        {index + 1}. {variantName(v, lang, t)}
      </h3>
      <ol className="flex flex-wrap items-center gap-1 text-sm">
        {v.years.map((y, i) => (
          <li key={y.index} className="flex items-center gap-1">
            <span
              className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                y.group === "legume" ? "bg-field-50 text-field-800" : y.group === "fallow" ? "bg-soil-50 text-soil-700" : y.group === "oilseed" ? "bg-wheat-100 text-soil-700" : "bg-surface-sunken text-ink-2"
              }`}
              title={`${y.year}`}
            >
              {cropName(y.crop, lang)}
            </span>
            {i < v.years.length - 1 && <span aria-hidden className="text-ink-subtle">→</span>}
          </li>
        ))}
      </ol>
      <div className="space-y-2.5">
        {KEYS.map((k) => (
          <ScoreRow key={k} k={k} score={v.scores[k]} />
        ))}
      </div>
      <div className="mt-auto space-y-1 border-t border-line pt-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-sm">{t("result.compare.income_total", { years })}</span>
          <span className="text-lg font-semibold tabular-nums">
            {fmtInt(v.totals.income_kzt_ha)} <span className="text-sm font-normal">{t("result.compare.per_ha")}</span>
          </span>
        </div>
        <div className="text-right text-sm text-ink-muted">{t("result.compare.field_total", { value: fmtInt(v.totals.income_field_kzt) })}</div>
        {diff !== null && (
          <div className="text-right text-sm font-medium">
            {t("result.compare.vs_base", { sign: "", value: fmtSigned(diff) })}
          </div>
        )}
        <div className="flex flex-col items-start gap-2 pt-1 text-sm">
          <span title={t("result.compare.weighted_hint", {
            priority: comparison.priority_name[lang],
            soil: comparison.weights.soil, water: comparison.weights.water, income: comparison.weights.income, risk: comparison.weights.risk,
          })}>
            {t("result.compare.weighted")}: <b>{fmtNum(v.weighted_score, 2)}</b>
          </span>
          <span className="badge-amber" title={t("app.needs_check_title")}>
            <AlertTriangle className="h-3 w-3" /> {t("result.compare.assumptions", { n: v.assumptions_used, total: v.params_used })}
          </span>
        </div>
      </div>
    </article>
  );
}

export function CustomVariantBuilder({
  horizon,
  initial,
  onApply,
  onRemove,
  active,
}: {
  horizon: number;
  initial: string[];
  onApply: (crops: string[]) => void;
  onRemove: () => void;
  active: boolean;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { config } = useConfig();
  const [crops, setCrops] = useState<string[]>(() => Array.from({ length: horizon }, (_, i) => initial[i % initial.length] ?? "wheat"));
  if (!config) return null;
  const list = Array.from({ length: horizon }, (_, i) => crops[i] ?? "wheat");
  return (
    <div className="card space-y-3">
      <h3 className="h3">{t("result.compare.custom_title")}</h3>
      <div className="grid gap-2 sm:grid-cols-5">
        {list.map((c, i) => (
          <label key={i} className="block">
            <span className="label">{t("result.compare.chain_year", { n: i + 1 })}</span>
            <select
              className="input"
              value={c}
              onChange={(e) => setCrops(list.map((x, j) => (j === i ? e.target.value : x)))}
            >
              {config.crops.map((cr) => (
                <option key={cr.id} value={cr.id}>
                  {cr.name[lang]}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-primary" onClick={() => onApply(list)}>
          {active ? t("result.compare.custom_recalc") : t("result.compare.custom_add")}
        </button>
        {active && (
          <button type="button" className="btn-secondary" onClick={onRemove}>
            {t("result.compare.custom_remove")}
          </button>
        )}
      </div>
    </div>
  );
}

export default function VariantCards({ comparison }: { comparison: Comparison }) {
  const { i18n } = useTranslation();
  const lang = i18n.language as Lang;
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {comparison.variants.map((v, i) => (
        <Card key={v.id} v={v} index={i} comparison={comparison} lang={lang} />
      ))}
    </div>
  );
}
