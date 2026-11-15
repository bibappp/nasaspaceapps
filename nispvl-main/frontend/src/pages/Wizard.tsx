import type { Polygon } from "geojson";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Analysis, CompareRequest, Comparison, DemoField, HistoryItem, Job, Lang, Variant } from "../api/types";
import { bareSoilLine } from "../components/planner/bareSoilMetrics";
import Disclaimer from "../components/common/Disclaimer";
import Spinner from "../components/common/Spinner";
import ResultMap from "../components/map/ResultMap";
import DataSummary, { Warnings } from "../components/results/DataSummary";
import ForecastCharts from "../components/results/ForecastCharts";
import PdfPanel from "../components/results/PdfPanel";
import StressTest from "../components/results/StressTest";
import VariantCards, { CustomVariantBuilder, variantName } from "../components/results/VariantCards";
import StepField from "../components/wizard/StepField";
import StepHistory from "../components/wizard/StepHistory";
import { useConfig } from "../lib/config";
import { areaHa, bboxOf } from "../lib/geo";

type Step = 0 | 1 | 2;

function defaultHistory(): HistoryItem[] {
  const y = new Date().getFullYear();
  return [4, 3, 2, 1, 0].map((d) => ({ year: y - d, crop: "wheat" }));
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-4 space-y-3">
      <h2 className="h2">{title}</h2>
      {children}
    </section>
  );
}

function pendingJobs(a: Analysis): Job[] {
  return [a.ndvi.state, a.soil_moisture.state].filter((s) => s.status === "pending" && s.job).map((s) => s.job as Job);
}

function Results({ request, customCrops, onCustom }: { request: CompareRequest; customCrops: string[] | null; onCustom: (c: string[] | null) => void }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { config } = useConfig();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stressIdx, setStressIdx] = useState<number | null>(null);
  const [version, setVersion] = useState(0);

  const fullRequest = useMemo<CompareRequest>(() => {
    if (!config) return request;
    const variants: Variant[] = config.default_variants.map((v) => ({ ...v }));
    if (customCrops) variants.push({ id: "custom", crops: customCrops, custom: true });
    return { ...request, variants };
  }, [request, customCrops, config]);

  useEffect(() => {
    let alive = true;
    setError(null);
    (async () => {
      try {
        const a = await api.analyze(request);
        if (!alive) return;
        setAnalysis(a);
        setJobs(pendingJobs(a));
        const c = await api.compare(fullRequest);
        if (alive) setComparison(c);
      } catch (e) {
        if (!alive) return;
        const err = e as ApiError;
        setError(err.status === 0 ? t("app.network_error") : err.detail);
      }
    })();
    return () => {
      alive = false;
    };
  }, [request, fullRequest, version, t]);

  // Опрос фоновых задач (NDVI MODIS, SMAP): по завершении пересчитываем
  const jobsKey = jobs.map((j) => j.id).join("|");
  const timer = useRef<number>();
  useEffect(() => {
    if (!jobs.length) return;
    const tick = async () => {
      const fresh = await Promise.all(jobs.map((j) => api.job(j.id).catch(() => ({ ...j, status: "failed" as const }))));
      setJobs(fresh.filter((j) => j.status === "running"));
      if (fresh.some((j) => j.status !== "running")) setVersion((v) => v + 1);
    };
    timer.current = window.setInterval(() => void tick(), 3000);
    return () => window.clearInterval(timer.current);
  }, [jobsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return (
      <div className="card border-red-300 bg-red-50">
        <h2 className="h3 text-red-900">{t("result.failed")}</h2>
        <p className="mt-1">{error}</p>
        <button type="button" className="btn-secondary mt-3" onClick={() => setVersion((v) => v + 1)}>{t("app.retry")}</button>
      </div>
    );
  }
  if (!analysis) return <Spinner label={t("result.calculating")} />;

  const ndviJob = jobs.find((j) => j.kind === "modis");
  const smapJob = jobs.find((j) => j.kind === "smap");
  const best = comparison?.variants.find((v) => v.fits_priority);

  return (
    <div className="space-y-10">
      <nav className="flex flex-wrap gap-2 text-sm" aria-label={t("result.title")}>
        {(["data", "map", "compare", "forecast", "stress", "explain", "pdf"] as const).map((s) => (
          <a key={s} href={`#r-${s}`} className="rounded-full bg-white px-3 py-1.5 font-semibold no-underline shadow-sm">{t(`result.sections.${s}`)}</a>
        ))}
      </nav>
      {(ndviJob || smapJob) && (
        <div className="card space-y-2 border-field-300 bg-field-50" role="status">
          {ndviJob && <Spinner label={t("result.pending_ndvi", { year: new Date().getFullYear(), done: ndviJob.done, total: ndviJob.total || "…" })} />}
          {smapJob && <Spinner label={t("result.pending_smap", { done: smapJob.done, total: smapJob.total || "…" })} />}
        </div>
      )}

      <Section id="r-data" title={t("result.sections.data")}>
        <DataSummary analysis={analysis} />
        <Warnings analysis={analysis} />
      </Section>

      <Section id="r-map" title={t("result.sections.map")}>
        <ResultMap field={analysis.field.geometry} bbox={analysis.field.bbox} key={`${analysis.field.bbox.join(",")}-${version}`} />
      </Section>

      {!comparison ? (
        <Spinner label={t("result.calculating")} />
      ) : (
        <>
          <Section id="r-compare" title={t("result.sections.compare")}>
            <VariantCards comparison={comparison} />
            <CustomVariantBuilder
              horizon={request.horizon_years}
              initial={customCrops ?? config?.default_variants[1]?.crops ?? ["wheat"]}
              active={!!customCrops}
              onApply={(c) => onCustom(c)}
              onRemove={() => onCustom(null)}
            />
          </Section>

          <Section id="r-forecast" title={t("result.sections.forecast")}>
            <ForecastCharts comparison={comparison} />
          </Section>

          <Section id="r-stress" title={t("result.sections.stress")}>
            <StressTest comparison={comparison} yearIndex={stressIdx} onYearIndex={setStressIdx} />
          </Section>

          <Section id="r-explain" title={t("result.sections.explain")}>
            <div className="grid gap-4 lg:grid-cols-2">
              {[...comparison.variants]
                .sort((a, b) => Number(b.fits_priority) - Number(a.fits_priority))
                .map((v) => (
                  <article key={v.id} className={`card ${v.fits_priority ? "ring-2 ring-field-300" : ""}`}>
                    <h3 className="h3 mb-2">
                      
                      {variantName(v, lang, t)}
                    </h3>
                    <ul className="list-disc space-y-1.5 pl-5">
                      {v.explanation.map((e, i) => (
                        <li key={`${e.code}-${i}`} className={e.code === "assumptions" ? "text-sm text-amber-900" : ""}>{e[lang]}</li>
                      ))}
                      {(() => {
                        const line = bareSoilLine(v, t);
                        return line ? <li>{line}</li> : null;
                      })()}
                    </ul>
                  </article>
                ))}
            </div>
            {best && <Disclaimer />}
          </Section>

          <Section id="r-pdf" title={t("result.sections.pdf")}>
            <PdfPanel request={fullRequest} comparison={comparison} stressYearIndex={stressIdx} key={comparison.best_variant_id} />
          </Section>
        </>
      )}
    </div>
  );
}

export default function Wizard() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { config, error: configError, reload } = useConfig();
  const [params] = useSearchParams();
  const [step, setStep] = useState<Step>(0);
  const [geometry, setGeometry] = useState<Polygon | null>(null);
  const [region, setRegion] = useState("akmola");
  const [history, setHistory] = useState<HistoryItem[]>(defaultHistory);
  const [priority, setPriority] = useState("max_income");
  const [horizon, setHorizon] = useState(4);
  const [demo, setDemo] = useState<DemoField | null>(null);
  const [submitted, setSubmitted] = useState<CompareRequest | null>(null);
  const [customCrops, setCustomCrops] = useState<string[] | null>(null);

  const loadDemo = useCallback(async () => {
    const d = await api.demo();
    setDemo(d);
    setGeometry(d.geometry);
    setRegion(d.region);
    setHistory(d.history);
    setPriority(d.priority);
    setHorizon(d.horizon_years);
    setCustomCrops(null);
    setSubmitted({ geometry: d.geometry, region: d.region, history: d.history, priority: d.priority, horizon_years: d.horizon_years });
    setStep(2);
  }, []);

  useEffect(() => {
    if (params.get("demo") === "1") void loadDemo().catch(() => undefined);
  }, [params, loadDemo]);

  if (configError) {
    return (
      <div className="card border-red-300 bg-red-50">
        <p>{t("app.network_error")}</p>
        <button className="btn-secondary mt-3" onClick={reload}>{t("app.retry")}</button>
      </div>
    );
  }
  if (!config) return <Spinner label={t("app.loading")} />;

  const area = geometry ? areaHa(geometry) : 0;
  const fieldOk = !!geometry && area > 0.01 && area <= 50000;
  const isDemo = !!demo && JSON.stringify(demo.geometry) === JSON.stringify(geometry);
  const calculate = () => {
    if (!geometry) return;
    setSubmitted({ geometry, region, history, priority, horizon_years: horizon });
    setStep(2);
    window.scrollTo({ top: 0 });
  };

  return (
    <div className="space-y-6">
      <ol className="grid grid-cols-3 gap-2">
        {(["field", "history", "result"] as const).map((s, i) => (
          <li key={s}>
            <button
              type="button"
              disabled={i === 2 ? !submitted : i === 1 && !fieldOk}
              onClick={() => setStep(i as Step)}
              aria-current={step === i ? "step" : undefined}
              className={`w-full rounded-xl px-2 py-2 text-left text-sm font-semibold sm:text-base ${step === i ? "bg-field-700 text-white" : "bg-white text-field-800 disabled:text-ink-muted"}`}
            >
              <span className="mr-1">{i + 1}.</span> {t(`wizard.steps.${s}`)}
            </button>
          </li>
        ))}
      </ol>

      {step === 0 && (
        <>
          <StepField geometry={geometry} region={region} onGeometry={setGeometry} onRegion={setRegion} />
          <div className="flex justify-end">
            <button type="button" className="btn-primary" disabled={!fieldOk} onClick={() => setStep(1)}>{t("wizard.next")} →</button>
          </div>
        </>
      )}
      {step === 1 && (
        <>
          <StepHistory
            history={history}
            priority={priority}
            horizon={horizon}
            isDemo={isDemo}
            demoNote={demo?.history_note[lang]}
            onHistory={setHistory}
            onPriority={setPriority}
            onHorizon={setHorizon}
          />
          <div className="flex justify-between">
            <button type="button" className="btn-secondary" onClick={() => setStep(0)}>← {t("wizard.back")}</button>
            <button type="button" className="btn-primary" disabled={!fieldOk} onClick={calculate}>{t("wizard.calculate")}</button>
          </div>
        </>
      )}
      {step === 2 && submitted && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h1 className="h1">{t("result.title")}</h1>
            <button type="button" className="btn-secondary" onClick={() => setStep(1)}>← {t("wizard.back")}</button>
          </div>
          {isDemo && demo && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950">{demo.name[lang]} — {demo.history_note[lang]}</p>}
          <Results request={submitted} customCrops={customCrops} onCustom={setCustomCrops} key={JSON.stringify(bboxOf(submitted.geometry))} />
        </>
      )}
    </div>
  );
}
