import { Calculator, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { Analysis, AppConfig, FieldRecord, Lang, SavedAnalysis, ScoreWeights, Variant } from "../../api/types";
import { errorText } from "../../lib/async";
import { useConfig } from "../../lib/config";
import PriorityControls from "../planner/PriorityControls";
import Results from "../planner/Results";
import ScenarioEditor, { fitCrops } from "../planner/ScenarioEditor";
import { comparisonWeights, sameWeights } from "../planner/weights";
import { ErrorBox, Loading, Notice } from "../ui/ui";

function defaultStartYear(): number {
  const d = new Date();
  return d.getMonth() < 5 ? d.getFullYear() : d.getFullYear() + 1;
}

function initialVariants(config: AppConfig, horizon: number): Variant[] {
  return config.default_variants.map((v) => ({ ...v, crops: fitCrops(v.crops, horizon) }));
}

export default function Planner({ field, overview }: { field: FieldRecord; overview: Analysis | null }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { config } = useConfig();
  const [horizon, setHorizon] = useState(4);
  const [variants, setVariants] = useState<Variant[] | null>(null);
  const [priority, setPriority] = useState("balanced");
  const [weights, setWeights] = useState<ScoreWeights>({ soil: 0.25, water: 0.25, income: 0.25, risk: 0.25 });
  const [stressYear, setStressYear] = useState<number | "auto">("auto");
  const [saved, setSaved] = useState<SavedAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingLast, setLoadingLast] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // последний сохранённый анализ поля открывается сразу — с его сценариями и весами
  useEffect(() => {
    if (!config) return;
    let alive = true;
    api
      .fieldAnalyses(field.id)
      .then(async ({ analyses }) => {
        const last = analyses[0];
        if (!last) return null;
        return api.analysis(last.id);
      })
      .then((a) => {
        if (!alive) return;
        if (a) apply(a);
        else {
          const p = config.priorities.find((x) => x.id === "balanced") ?? config.priorities[0];
          if (p) {
            setPriority(p.id);
            setWeights({ ...p.weights });
          }
          setVariants(initialVariants(config, 4));
        }
      })
      .catch(() => alive && setVariants(initialVariants(config, 4)))
      .finally(() => alive && setLoadingLast(false));
    return () => {
      alive = false;
    };
  }, [config, field.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const apply = (a: SavedAnalysis) => {
    setSaved(a);
    setHorizon(a.result.horizon_years);
    setPriority(a.result.priority);
    setWeights(comparisonWeights(a.result));
    setVariants(a.result.variants.map((v) => ({ id: v.id, name: v.name ?? null, crops: v.crops, custom: v.custom })));
    setStressYear(a.request.stress_year ?? "auto");
  };

  if (!config || loadingLast || !variants) return <Loading />;
  const dryYears = overview?.drought.dry_years ?? [];
  const startYear = defaultStartYear();
  const preset = config.priorities.find((p) => p.id === priority);
  const custom = !preset || !sameWeights(preset.weights, weights);
  const weightsChanged = saved ? !sameWeights(comparisonWeights(saved.result), weights) : false;

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const a = await api.createAnalysis(field.id, {
        title: "",
        priority,
        weights: custom ? weights : null,
        horizon_years: horizon,
        variants: variants.map((v) => ({ ...v, crops: fitCrops(v.crops, horizon) })),
        stress_year: stressYear === "auto" ? null : stressYear,
      });
      apply(a);
    } catch (e) {
      setError(errorText(e, t));
    } finally {
      setBusy(false);
    }
  };
  const changeHorizon = (h: number) => {
    setHorizon(h);
    setVariants(variants.map((v) => ({ ...v, crops: fitCrops(v.crops, h) })));
  };

  return (
    <div className="space-y-6">
      {field.history_is_scenario && <Notice tone="warn">{t("planner.history_scenario")}</Notice>}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2 className="h3">{t("planner.scenarios_title")}</h2>
            <p className="text-xs text-ink-muted">{t("planner.scenarios_sub", { crop: field.history.at(-1)?.crop ? config.crops.find((c) => c.id === field.history.at(-1)?.crop)?.name[lang] : "—" })}</p>
          </div>
        </div>
        <div className="panel-body">
          <ScenarioEditor config={config} variants={variants} horizon={horizon} startYear={startYear} onChange={setVariants} />
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <section className="panel">
          <div className="panel-head"><h2 className="h3">{t("planner.priorities_title")}</h2></div>
          <div className="panel-body">
            <PriorityControls config={config} priority={priority} weights={weights} onChange={(p, w) => { setPriority(p); setWeights(w); }} />
          </div>
        </section>
        <section className="panel">
          <div className="panel-head"><h2 className="h3">{t("planner.settings_title")}</h2></div>
          <div className="panel-body space-y-4">
            <label className="block">
              <span className="label">{t("wizard.history.horizon")}</span>
              <div className="flex gap-1.5">
                {[3, 4, 5].map((h) => (
                  <button key={h} type="button" aria-pressed={horizon === h} onClick={() => changeHorizon(h)} className={horizon === h ? "btn-primary h-8 px-3" : "btn-secondary h-8 px-3"}>
                    {t("wizard.history.years", { count: h })}
                  </button>
                ))}
              </div>
            </label>
            <label className="block">
              <span className="label">{t("planner.stress_year")}</span>
              <select className="input" value={stressYear} onChange={(e) => setStressYear(e.target.value === "auto" ? "auto" : Number(e.target.value))}>
                <option value="auto">{t("planner.stress_auto")}</option>
                {[...dryYears].reverse().map((y) => (
                  <option key={y} value={y}>{y}{y === 2021 ? ` — ${t("planner.stress_2021")}` : ""}</option>
                ))}
              </select>
              <span className="hint">{t("planner.stress_hint", { years: dryYears.join(", ") || "—" })}</span>
            </label>
            <button type="button" className="btn-primary btn-lg w-full" disabled={busy || variants.length < 2} onClick={() => void run()}>
              <Calculator className="h-4 w-4" /> {busy ? t("result.calculating") : t("planner.calculate")}
            </button>
            <p className="hint">{t("planner.calculate_hint")}</p>
          </div>
        </section>
      </div>

      {error && <ErrorBox message={error} />}

      {saved && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-6">
            <div>
              <h2 className="h2">{t("planner.results_title")}</h2>
              <p className="text-sm text-ink-muted">
                {t("planner.results_saved")} <Link to={`/app/analyses/${saved.id}`}>#{saved.id}</Link>
              </p>
            </div>
            {weightsChanged && (
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                {t("planner.reranked")}
                <button type="button" className="btn-secondary h-8" disabled={busy} onClick={() => void run()}>
                  <Save className="h-4 w-4" /> {t("planner.save_weights")}
                </button>
              </div>
            )}
          </div>
          <Results comparison={saved.result} weights={weights} customWeights={custom} />
        </>
      )}
    </div>
  );
}
