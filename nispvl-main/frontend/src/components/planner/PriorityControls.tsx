import { useTranslation } from "react-i18next";
import type { AppConfig, Lang, ScoreWeights } from "../../api/types";
import { tx } from "../../lib/i18n-text";
import { normalize, SCORE_KEYS, sameWeights } from "./weights";

/** Пресеты приоритета и ползунки весов. Веса нормируются к сумме 1 — показываем итоговые доли. */
export default function PriorityControls({ config, priority, weights, onChange }: {
  config: AppConfig;
  priority: string;
  weights: ScoreWeights;
  onChange: (priority: string, weights: ScoreWeights) => void;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const norm = normalize(weights);
  const preset = config.priorities.find((p) => p.id === priority);
  const custom = !preset || !sameWeights(preset.weights, weights);
  return (
    <div className="space-y-4">
      <div>
        <div className="label">{t("planner.presets")}</div>
        <div className="flex flex-wrap gap-1.5">
          {config.priorities.map((p) => {
            const active = p.id === priority && !custom;
            return (
              <button key={p.id} type="button" aria-pressed={active} onClick={() => onChange(p.id, { ...p.weights })} className={active ? "btn-primary h-8 px-2.5 text-xs" : "btn-secondary h-8 px-2.5 text-xs"}>
                {tx(p.name, lang)}
              </button>
            );
          })}
        </div>
        {custom && <p className="hint">{t("planner.custom_weights")}</p>}
      </div>
      <div className="space-y-3">
        {SCORE_KEYS.map((k) => (
          <label key={k} className="block">
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="font-medium text-ink-2">{t(`result.scores.${k}`)}</span>
              <span className="tabular-nums text-ink">{Math.round(norm[k] * 100)} %</span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={Math.round(weights[k] * 100)}
              onChange={(e) => onChange(priority, { ...weights, [k]: Number(e.target.value) / 100 })}
              className="w-full accent-field-700"
              aria-valuetext={`${Math.round(norm[k] * 100)} %`}
            />
          </label>
        ))}
      </div>
      <p className="hint">{t("planner.weights_hint")}</p>
    </div>
  );
}
