import { useTranslation } from "react-i18next";
import type { Lang, SourceMeta } from "../../api/types";
import { tx } from "../../lib/i18n-text";

const KIND: Record<string, "observation" | "reanalysis" | "model"> = { power: "reanalysis", modis: "observation", smap: "observation", gpm: "observation", soilgrids: "model" };

/** Источники, использованные на экране: название, разрешение, происхождение, состояние. */
export default function SourceList({ sources, periods }: { sources: SourceMeta[]; periods?: Record<string, string> }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  return (
    <div className="panel overflow-x-auto">
      <table className="table min-w-[720px]">
        <thead>
          <tr>
            <th>{t("sources.col_source")}</th>
            <th>{t("sources.col_type")}</th>
            <th>{t("sources.col_resolution")}</th>
            <th>{t("sources.col_period")}</th>
            <th>{t("sources.col_status")}</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => {
            const notActive = s.state === "not_available" || s.origin === "unavailable" || s.origin === null;
            return (
              <tr key={s.id}>
                <td>
                  <div className="font-medium text-ink">{s.title}</div>
                  <div className="text-xs text-ink-muted">{tx(s.provenance, lang)}</div>
                </td>
                <td><span className="text-xs">{t(`kind.${KIND[s.id] ?? "observation"}`)}</span></td>
                <td className="text-xs text-ink-2">{tx(s.spatial_resolution, lang)}</td>
                <td className="whitespace-nowrap text-xs text-ink-2">{periods?.[s.id] ?? "—"}</td>
                <td>
                  {s.state === "not_available" ? (
                    <span className="badge-neutral">{t("sources.not_integrated")}</span>
                  ) : notActive ? (
                    <span className="badge-amber">{t("result.summary.origin.unavailable")}</span>
                  ) : (
                    <span className="badge-green">{t(`result.summary.origin.${s.origin}`)}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
