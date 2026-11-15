import { FileBarChart } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { Lang } from "../../api/types";
import { EmptyState, ErrorBox, Loading, PageHeader } from "../../components/ui/ui";
import { errorText, fmtDate, useAsync } from "../../lib/async";
import { useCropName } from "../../lib/config";
import { fmtInt } from "../../lib/format";

export default function Analyses() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const cropName = useCropName();
  const list = useAsync(() => api.recentAnalyses(100).then((r) => r.analyses), []);
  return (
    <div>
      <PageHeader title={t("analyses.title")} subtitle={t("analyses.subtitle")} />
      {list.error ? <ErrorBox message={errorText(list.error, t)} onRetry={list.reload} /> : null}
      {list.loading && !list.data && <Loading />}
      {list.data?.length === 0 && <EmptyState icon={<FileBarChart className="h-8 w-8" />} title={t("reports.none")} text={t("reports.none_hint")} />}
      {!!list.data?.length && (
        <div className="panel overflow-x-auto">
          <table className="table min-w-[760px]">
            <thead>
              <tr>
                <th>{t("reports.col_date")}</th>
                <th>{t("fields.col_name")}</th>
                <th>{t("reports.col_best")}</th>
                <th className="num">{t("planner.gross_margin")}</th>
                <th className="num">{t("planner.confidence")}</th>
              </tr>
            </thead>
            <tbody>
              {list.data.map((a) => {
                const best = a.summary.variants.find((v) => v.id === a.summary.best_variant_id);
                return (
                  <tr key={a.id}>
                    <td className="whitespace-nowrap"><Link to={`/app/analyses/${a.id}`}>#{a.id}</Link> · {fmtDate(a.created_at, lang)}</td>
                    <td><Link to={`/app/fields/${a.field_id}`} className="text-ink">{a.field_name}</Link></td>
                    <td>
                      <div className="font-medium">{a.summary.best_variant_name?.[lang] ?? a.summary.best_variant_id}</div>
                      <div className="text-xs text-ink-muted">{a.summary.best_crops.map((c) => cropName(c, lang)).join(" → ")}</div>
                    </td>
                    <td className="num">{best ? fmtInt(best.gross_margin_kzt_ha) : "—"}</td>
                    <td className="num text-xs">{best ? t(`planner.conf.${best.confidence}`) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
