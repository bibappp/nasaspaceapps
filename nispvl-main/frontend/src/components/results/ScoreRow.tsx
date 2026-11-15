import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Score, ScoreKey } from "../../api/types";
import { fmtInt, fmtNum } from "../../lib/format";
import StatusBadge from "../common/StatusBadge";


// единица метрики оценки -> ключ перевода (метрики заданы в backend/app/model/rotation.py)
const METRIC_UNIT: Record<string, string> = { income_kzt_ha: "units.kzt_ha", water_deficit_mean_mm: "units.mm" };

function fmtMetric(v: number): string {
  return Math.abs(v) >= 1000 ? fmtInt(v) : fmtNum(v, 1);
}

/** Оценка 1–5 полосой + раскрывающаяся подсказка: формула, входные данные, правила с источниками. */
export default function ScoreRow({ k, score }: { k: ScoreKey; score: Score }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const id = useId();
  const pct = ((score.score - 1) / 4) * 100;
  const name = t(`result.scores.${k}`);
  const unitKey = METRIC_UNIT[score.metric];
  const unit = unitKey ? t(unitKey) : score.metric === "drought_loss_pct" ? "%" : "";
  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="w-20 flex-none text-sm font-medium text-ink-2">{name}</span>
        <div className="relative h-2 flex-1 rounded-full bg-surface-sunken" aria-hidden>
          <div className="absolute inset-y-0 left-0 rounded-full bg-field-600" style={{ width: `${Math.max(4, pct)}%` }} />
        </div>
        <span className="w-14 flex-none text-right text-sm font-semibold tabular-nums">
          {fmtNum(score.score, 1)}
          <span className="text-xs font-normal text-ink-muted">/5</span>
        </span>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          aria-label={t("result.scores.tooltip_title", { name })}
          className={`flex h-6 w-6 flex-none items-center justify-center rounded-full border text-xs font-semibold ${score.assumptions > 0 ? "border-amber-300 bg-amber-50 text-amber-800" : "border-line-strong text-ink-2"} hover:bg-surface-sunken`}
          onClick={() => setOpen((o) => !o)}
        >
          {score.assumptions > 0 ? "!" : "i"}
        </button>
      </div>
      {open && (
        <div id={id} className="mt-2 space-y-2 rounded-md border border-line bg-surface p-3 text-sm">
          <div className="font-semibold">{t("result.scores.tooltip_title", { name })}</div>
          <div>
            <b>{t("result.scores.formula")}:</b> {t(`result.scores.formula_${k}`)}
          </div>
          <div>
            <b>{t("result.scores.inputs")}:</b> {t("result.scores.value", { value: fmtMetric(score.value), unit })} (
            {t(score.better === "higher" ? "result.scores.better_higher" : "result.scores.better_lower")})
          </div>
          <div>
            {t("result.scores.scale", {
              min: fmtMetric(score.better === "higher" ? score.scale_min : score.scale_max),
              max: fmtMetric(score.better === "higher" ? score.scale_max : score.scale_min),
              n: score.pool_size,
            })}
          </div>
          <div className="font-semibold">{t("result.scores.rules")}:</div>
          <ul className="max-h-56 space-y-1.5 overflow-y-auto pr-1">
            {score.params.map((p) => (
              <li key={p.path} className="rounded border border-line bg-white px-2 py-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="text-xs">{p.path}</code>
                  <span className="font-semibold">
                    = {typeof p.value === "object" ? JSON.stringify(p.value) : String(p.value)} {p.unit}
                  </span>
                  <StatusBadge status={p.status} />
                  <span className="text-xs text-ink-muted">{t(`methodology.evidence.${p.evidence}`)}</span>
                </div>
                <div className="text-xs text-ink-muted">
                  {t("app.source")}:{" "}
                  {p.url.startsWith("http") ? (
                    <a href={p.url} target="_blank" rel="noreferrer">{p.source}</a>
                  ) : (
                    <span>{p.source} ({p.url})</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
