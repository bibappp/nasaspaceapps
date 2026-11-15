import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import { errorText, useAsync } from "../../lib/async";
import { fmtNum } from "../../lib/format";
import { ErrorBox, KindBadge, LevelBadge, Loading, Notice, SectionTitle } from "../ui/ui";
import { RiskGrid } from "./RiskCards";

export default function RiskTab({ fieldId }: { fieldId: number }) {
  const { t } = useTranslation();
  const r = useAsync(() => api.fieldRisk(fieldId), [fieldId]);
  if (r.error) return <ErrorBox message={errorText(r.error, t)} onRetry={r.reload} />;
  if (!r.data) return <Loading />;
  const risk = r.data;
  return (
    <div className="space-y-6">
      <div className="panel flex flex-wrap items-center gap-4 p-4">
        <div>
          <div className="text-xs text-ink-muted">{t("risk.overall", { season: risk.latest_season })}</div>
          <div className="mt-1"><LevelBadge level={risk.overall} /></div>
        </div>
        <p className="min-w-0 flex-1 text-sm text-ink-2">{t("risk.overall_hint")}</p>
      </div>
      <RiskGrid risk={risk} />
      <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-ink-muted">
        {(["observation", "reanalysis", "statistic", "model"] as const).map((k) => (
          <span key={k} className="flex items-center gap-1.5"><KindBadge kind={k} /> {t(`kind.${k}_hint`)}</span>
        ))}
      </div>
      <Notice>{t("risk.not_forecast")}</Notice>
      <section>
        <SectionTitle title={t("risk.thresholds_title")} hint={t("risk.thresholds_hint")} />
        <div className="panel overflow-x-auto">
          <table className="table min-w-[640px]">
            <thead>
              <tr>
                <th>{t("risk.threshold")}</th>
                <th className="num">{t("methodology.col_value")}</th>
                <th>{t("methodology.evidence_title")}</th>
                <th>{t("methodology.col_source")}</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(risk.thresholds).map(([k, p]) => (
                <tr key={k}>
                  <td><code className="text-xs">{p.path}</code></td>
                  <td className="num">{typeof p.value === "number" ? fmtNum(p.value, Math.abs(p.value) < 1 ? 2 : 1) : String(p.value)} {p.unit}</td>
                  <td><span className={p.evidence === "literature" || p.evidence === "definition" ? "badge-green" : "badge-amber"}>{t(`methodology.evidence.${p.evidence}`)}</span></td>
                  <td className="text-xs">{p.url?.startsWith("http") ? <a href={p.url} target="_blank" rel="noreferrer">{p.source}</a> : p.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
