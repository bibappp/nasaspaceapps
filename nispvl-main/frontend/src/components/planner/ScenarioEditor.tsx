import { Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AppConfig, Lang, Variant } from "../../api/types";
import { seriesColor } from "../../lib/colors";
import { tx } from "../../lib/i18n-text";

export const MAX_VARIANTS = 4;
const LETTERS = "ABCDEF";

export function fitCrops(crops: string[], horizon: number): string[] {
  return Array.from({ length: horizon }, (_, i) => crops[i] ?? crops[i % Math.max(1, crops.length)] ?? "wheat");
}

/** Редактор сценариев: 2–4 севооборота, культура на каждый год плана. Первый — базовый («как сейчас»). */
export default function ScenarioEditor({ config, variants, horizon, startYear, onChange }: {
  config: AppConfig;
  variants: Variant[];
  horizon: number;
  startYear: number;
  onChange: (v: Variant[]) => void;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const update = (i: number, patch: Partial<Variant>) => onChange(variants.map((v, j) => (j === i ? { ...v, ...patch } : v)));
  const used = new Set(variants.map((v) => v.id));
  const addable = config.default_variants.filter((d) => !used.has(d.id));
  const add = () => {
    const next = addable[0];
    if (next) onChange([...variants, { ...next, crops: fitCrops(next.crops, horizon) }]);
    else {
      let n = 1;
      while (used.has(`custom_${n}`)) n++;
      onChange([...variants, { id: `custom_${n}`, crops: fitCrops(["wheat"], horizon), custom: true, name: null }]);
    }
  };
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="table min-w-[640px]">
          <thead>
            <tr>
              <th className="w-[34%]">{t("planner.scenario")}</th>
              {Array.from({ length: horizon }, (_, i) => (
                <th key={i}>{startYear + i}</th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {variants.map((v, i) => (
              <tr key={v.id}>
                <td>
                  <div className="flex items-center gap-2">
                    <span className="inline-flex h-6 w-6 flex-none items-center justify-center rounded text-xs font-semibold text-white" style={{ background: seriesColor(i) }}>
                      {LETTERS[i]}
                    </span>
                    {v.custom ? (
                      <input
                        className="input h-8"
                        maxLength={60}
                        value={v.name?.[lang] ?? ""}
                        placeholder={t("result.compare.custom_name")}
                        onChange={(e) => update(i, { name: { ru: e.target.value, kk: e.target.value, en: e.target.value } })}
                        aria-label={t("planner.scenario_name")}
                      />
                    ) : (
                      <span className="text-sm font-medium">{tx(v.name, lang) || v.id}</span>
                    )}
                  </div>
                  {i === 0 && <div className="mt-1 pl-8 text-xs text-ink-muted">{t("planner.baseline")}</div>}
                </td>
                {fitCrops(v.crops, horizon).map((c, y) => (
                  <td key={y}>
                    <select
                      className="input h-8 min-w-[110px] px-2"
                      value={c}
                      aria-label={`${LETTERS[i]} ${startYear + y}`}
                      onChange={(e) => {
                        const crops = fitCrops(v.crops, horizon).map((x, j) => (j === y ? e.target.value : x));
                        update(i, { crops, custom: v.custom || crops.join() !== fitCrops(config.default_variants.find((d) => d.id === v.id)?.crops ?? [], horizon).join() });
                      }}
                    >
                      {config.crops.map((cr) => (
                        <option key={cr.id} value={cr.id}>{cr.short[lang]}</option>
                      ))}
                    </select>
                  </td>
                ))}
                <td className="text-right">
                  {variants.length > 2 && (
                    <button type="button" className="btn-icon btn-ghost" aria-label={t("planner.remove_scenario")} onClick={() => onChange(variants.filter((_, j) => j !== i))}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-secondary h-8" disabled={variants.length >= MAX_VARIANTS} onClick={add}>
          <Plus className="h-4 w-4" /> {t("planner.add_scenario")}
        </button>
        <button type="button" className="btn-ghost h-8" onClick={() => onChange(config.default_variants.map((d) => ({ ...d, crops: fitCrops(d.crops, horizon) })))}>
          {t("planner.reset_scenarios")}
        </button>
        <span className="hint mt-0">{t("planner.scenarios_hint", { max: MAX_VARIANTS })}</span>
      </div>
    </div>
  );
}
