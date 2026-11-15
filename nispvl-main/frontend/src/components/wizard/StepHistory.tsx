import { useTranslation } from "react-i18next";
import type { HistoryItem, Lang } from "../../api/types";
import { useConfig } from "../../lib/config";

interface Props {
  history: HistoryItem[];
  priority: string;
  horizon: number;
  isDemo: boolean;
  demoNote?: string;
  onHistory: (h: HistoryItem[]) => void;
  onPriority: (p: string) => void;
  onHorizon: (n: number) => void;
}

export default function StepHistory({ history, priority, horizon, isDemo, demoNote, onHistory, onPriority, onHorizon }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { config } = useConfig();
  if (!config) return null;
  const sorted = [...history].sort((a, b) => a.year - b.year);
  const maxYears = config.history.max_years;
  const minYears = config.history.min_years;
  const crops = config.crops;

  const setCrop = (year: number, crop: string) => onHistory(history.map((h) => (h.year === year ? { ...h, crop } : h)));
  const addYear = () => {
    const first = sorted[0]?.year ?? new Date().getFullYear();
    onHistory([{ year: first - 1, crop: "wheat" }, ...history]);
  };
  const removeYear = (year: number) => onHistory(history.filter((h) => h.year !== year));

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <h2 className="h2">{t("wizard.history.title")}</h2>
        <p className="muted">{t("wizard.history.hint")}</p>
        {isDemo && demoNote && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950">{demoNote}</p>}
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-left">
            <thead className="bg-surface text-sm">
              <tr>
                <th className="px-4 py-2">{t("wizard.history.year")}</th>
                <th className="px-4 py-2">{t("wizard.history.crop")}</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((h) => (
                <tr key={h.year} className="border-t">
                  <td className="px-4 py-2 text-lg font-semibold">{h.year}</td>
                  <td className="px-4 py-2">
                    <select
                      className="input"
                      aria-label={`${t("wizard.history.crop")} ${h.year}`}
                      value={h.crop}
                      onChange={(e) => setCrop(h.year, e.target.value)}
                    >
                      {crops.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name[lang]} ({t(`groups.${c.group}`)})
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      type="button"
                      className="btn-ghost"
                      disabled={history.length <= minYears}
                      onClick={() => removeYear(h.year)}
                    >
                      {t("wizard.history.remove")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button type="button" className="btn-secondary" disabled={history.length >= maxYears} onClick={addYear}>
          + {t("wizard.history.add")}
        </button>
      </section>

      <section className="space-y-3">
        <h2 className="h2">{t("wizard.history.priority_title")}</h2>
        <p className="muted">{t("wizard.history.priority_hint")}</p>
        <div className="grid gap-3 sm:grid-cols-3" role="radiogroup">
          {config.priorities.map((p) => (
            <label
              key={p.id}
              className={`card flex cursor-pointer items-start gap-3 border-2 ${priority === p.id ? "border-field-700 bg-field-50" : ""}`}
            >
              <input type="radio" name="priority" className="mt-1.5 h-5 w-5 accent-field-700" checked={priority === p.id} onChange={() => onPriority(p.id)} />
              <span>
                <span className="block text-lg font-semibold">{p.name[lang]}</span>
                <span className="text-sm text-ink-muted">
                  {(["income", "water", "soil", "risk"] as const).map((k) => `${t(`result.scores.${k}`)} ${Math.round(p.weights[k] * 100)} %`).join(" · ")}
                </span>
              </span>
            </label>
          ))}
        </div>
      </section>

      <label className="block max-w-xs">
        <span className="label">{t("wizard.history.horizon")}</span>
        <select className="input" value={horizon} onChange={(e) => onHorizon(Number(e.target.value))}>
          {Array.from({ length: config.horizon.max_years - config.horizon.min_years + 1 }, (_, i) => config.horizon.min_years + i).map((n) => (
            <option key={n} value={n}>
              {t("wizard.history.years", { count: n })}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
