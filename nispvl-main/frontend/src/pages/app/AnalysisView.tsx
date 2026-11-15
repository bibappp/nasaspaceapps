import { ArrowLeft, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { Lang, ScoreWeights } from "../../api/types";
import PriorityControls from "../../components/planner/PriorityControls";
import Results from "../../components/planner/Results";
import { comparisonWeights, sameWeights } from "../../components/planner/weights";
import { variantName } from "../../components/results/VariantCards";
import { ExportButtons } from "../../components/workspace/Reports";
import { ErrorBox, Loading, PageHeader } from "../../components/ui/ui";
import { errorText, fmtDate, useAsync } from "../../lib/async";
import { useConfig } from "../../lib/config";

/** Сохранённый анализ: те же результаты, что в планировщике; веса можно подвигать для «что если» без пересохранения. */
export default function AnalysisView() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { id } = useParams();
  const navigate = useNavigate();
  const { config } = useConfig();
  const a = useAsync(() => api.analysis(Number(id)), [id]);
  const [weights, setWeights] = useState<ScoreWeights | null>(null);
  const [priority, setPriority] = useState<string | null>(null);
  if (a.error) return <ErrorBox message={errorText(a.error, t)} onRetry={a.reload} />;
  if (!a.data || !config) return <Loading />;
  const s = a.data;
  const w = weights ?? comparisonWeights(s.result);
  const p = priority ?? s.result.priority;
  const preset = config.priorities.find((x) => x.id === p);
  const remove = async () => {
    if (!window.confirm(t("reports.delete_confirm"))) return;
    await api.deleteAnalysis(s.id);
    navigate(`/app/fields/${s.field_id}?tab=reports`);
  };
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={<Link to={`/app/fields/${s.field_id}?tab=reports`} className="inline-flex items-center gap-1 text-ink-muted no-underline hover:text-ink"><ArrowLeft className="h-3.5 w-3.5" /> {s.field_name}</Link>}
        title={t("analysis.title", { id: s.id })}
        subtitle={t("analysis.subtitle", { date: fmtDate(s.created_at, lang), from: s.result.start_year, to: s.result.start_year + s.result.horizon_years - 1, year: s.result.conditions.dry_year })}
        actions={<button type="button" className="btn-danger" onClick={() => void remove()}><Trash2 className="h-4 w-4" /> {t("reports.delete")}</button>}
      />
      <section className="panel">
        <div className="panel-head"><h2 className="h3">{t("reports.export_title")}</h2></div>
        <div className="panel-body">
          <ExportButtons fieldId={s.field_id} analysisId={s.id} variants={s.result.variants.map((v) => ({ id: v.id, label: variantName(v, lang, t) }))} />
        </div>
      </section>
      <details className="panel">
        <summary className="panel-head cursor-pointer select-none">
          <span className="h3">{t("analysis.whatif")}</span>
          {!sameWeights(w, comparisonWeights(s.result)) && <span className="badge-amber">{t("planner.reranked_short")}</span>}
        </summary>
        <div className="panel-body max-w-xl">
          <PriorityControls config={config} priority={p} weights={w} onChange={(np, nw) => { setPriority(np); setWeights(nw); }} />
          <p className="hint">{t("analysis.whatif_hint")}</p>
        </div>
      </details>
      <Results comparison={s.result} weights={w} customWeights={!preset || !sameWeights(preset.weights, w)} />
    </div>
  );
}
