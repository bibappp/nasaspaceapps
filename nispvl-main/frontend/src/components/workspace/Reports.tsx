import { Download, FileSpreadsheet, FileText, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { Lang } from "../../api/types";
import { errorText, fmtDate, useAsync } from "../../lib/async";
import { useCropName } from "../../lib/config";
import { fmtInt, fmtNum } from "../../lib/format";
import { EmptyState, ErrorBox, Loading, Notice, SectionTitle } from "../ui/ui";

const LANGS: Lang[] = ["ru", "kk", "en"];

/** Кнопки экспорта: PDF и XLSX строятся на сервере по сохранённому анализу (или по текущим данным поля). */
export function ExportButtons({ fieldId, analysisId, variants }: { fieldId: number; analysisId?: number; variants?: { id: string; label: string }[] }) {
  const { t, i18n } = useTranslation();
  const [lang, setLang] = useState<Lang>(i18n.language as Lang);
  const [variant, setVariant] = useState<string>("");
  const [busy, setBusy] = useState<"pdf" | "xlsx" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const go = async (kind: "pdf" | "xlsx") => {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "pdf") await api.downloadPdf(fieldId, lang, analysisId, variant || undefined);
      else await api.downloadXlsx(fieldId, lang, analysisId);
    } catch (e) {
      setError(errorText(e, t));
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="label">{t("reports.lang")}</span>
          <select className="input h-9 w-36" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
            {LANGS.map((l) => <option key={l} value={l}>{t(`app.lang.${l}_name`)}</option>)}
          </select>
        </label>
        {variants && variants.length > 0 && (
          <label className="block">
            <span className="label">{t("result.pdf.variant")}</span>
            <select className="input h-9 w-64" value={variant} onChange={(e) => setVariant(e.target.value)}>
              <option value="">{t("reports.variant_best")}</option>
              {variants.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          </label>
        )}
        <button type="button" className="btn-primary h-9" disabled={!!busy} onClick={() => void go("pdf")}>
          <FileText className="h-4 w-4" /> {busy === "pdf" ? t("reports.preparing") : t("reports.pdf")}
        </button>
        <button type="button" className="btn-secondary h-9" disabled={!!busy} onClick={() => void go("xlsx")}>
          <FileSpreadsheet className="h-4 w-4" /> {busy === "xlsx" ? t("reports.preparing") : t("reports.xlsx")}
        </button>
      </div>
      {lang === "kk" && <p className="hint">{t("reports.kk_note")}</p>}
      {error && <ErrorBox message={error} />}
    </div>
  );
}

export default function Reports({ fieldId }: { fieldId: number }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const cropName = useCropName();
  const list = useAsync(() => api.fieldAnalyses(fieldId).then((r) => r.analyses), [fieldId]);
  const remove = async (id: number) => {
    if (!window.confirm(t("reports.delete_confirm"))) return;
    await api.deleteAnalysis(id).catch(() => undefined);
    list.reload();
  };
  return (
    <div className="space-y-8">
      <section className="panel">
        <div className="panel-head">
          <h2 className="h3">{t("reports.current_title")}</h2>
        </div>
        <div className="panel-body space-y-3">
          <p className="text-sm text-ink-muted">{t("reports.current_hint")}</p>
          <ExportButtons fieldId={fieldId} />
          <Notice>{t("reports.contents")}</Notice>
        </div>
      </section>
      <section>
        <SectionTitle title={t("reports.saved_title")} hint={t("reports.saved_hint")} />
        {list.error ? <ErrorBox message={errorText(list.error, t)} onRetry={list.reload} /> : null}
        {list.loading && !list.data && <Loading />}
        {list.data?.length === 0 && <EmptyState title={t("reports.none")} text={t("reports.none_hint")} />}
        {!!list.data?.length && (
          <div className="panel overflow-x-auto">
            <table className="table min-w-[760px]">
              <thead>
                <tr>
                  <th>{t("reports.col_date")}</th>
                  <th>{t("reports.col_best")}</th>
                  <th>{t("reports.col_weights")}</th>
                  <th className="num">{t("planner.gross_margin")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.data.map((a) => {
                  const best = a.summary.variants.find((v) => v.id === a.summary.best_variant_id);
                  const w = a.summary.weights;
                  return (
                    <tr key={a.id}>
                      <td className="whitespace-nowrap">
                        <Link to={`/app/analyses/${a.id}`}>#{a.id}</Link> · {fmtDate(a.created_at, lang)}
                        <div className="text-xs text-ink-muted">{a.summary.start_year}–{a.summary.start_year + a.summary.horizon_years - 1} · {t("planner.stress_short", { year: a.summary.stress_year })}</div>
                      </td>
                      <td>
                        <div className="font-medium">{a.summary.best_variant_name?.[lang] ?? a.summary.best_variant_id}</div>
                        <div className="text-xs text-ink-muted">{a.summary.best_crops.map((c) => cropName(c, lang)).join(" → ")}</div>
                      </td>
                      <td className="text-xs text-ink-2">
                        {(["soil", "water", "income", "risk"] as const).map((k) => `${t(`result.scores.${k}`)} ${fmtNum(w[k] * 100, 0)}%`).join(" · ")}
                        {a.summary.weights_custom && <span className="badge-neutral ml-1">{t("planner.custom")}</span>}
                      </td>
                      <td className="num">{best ? fmtInt(best.gross_margin_kzt_ha) : "—"}</td>
                      <td className="whitespace-nowrap text-right">
                        <button type="button" className="btn-ghost h-8" onClick={() => void api.downloadPdf(fieldId, lang, a.id)}><Download className="h-3.5 w-3.5" /> PDF</button>
                        <button type="button" className="btn-ghost h-8" onClick={() => void api.downloadXlsx(fieldId, lang, a.id)}><Download className="h-3.5 w-3.5" /> XLSX</button>
                        <button type="button" className="btn-icon btn-ghost" aria-label={t("reports.delete")} onClick={() => void remove(a.id)}><Trash2 className="h-4 w-4" /></button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
