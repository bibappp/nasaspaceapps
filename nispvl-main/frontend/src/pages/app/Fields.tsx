import { ArrowRight, Map as MapIcon, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { Lang } from "../../api/types";
import FieldThumb from "../../components/fields/FieldThumb";
import { EmptyState, ErrorBox, Loading, PageHeader } from "../../components/ui/ui";
import { errorText, fmtDate, useAsync } from "../../lib/async";
import { useConfig, useCropName } from "../../lib/config";
import { fmtNum } from "../../lib/format";
import { tx } from "../../lib/i18n-text";

export default function Fields() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { config } = useConfig();
  const cropName = useCropName();
  const fields = useAsync(() => api.fields().then((r) => r.fields), []);
  const add = (
    <Link to="/app/fields/new" className="btn-primary no-underline">
      <Plus className="h-4 w-4" /> {t("fields.add")}
    </Link>
  );
  return (
    <div>
      <PageHeader title={t("fields.title")} subtitle={t("fields.subtitle")} actions={add} />
      {fields.error ? <ErrorBox message={errorText(fields.error, t)} onRetry={fields.reload} /> : null}
      {fields.loading && !fields.data && <Loading />}
      {fields.data?.length === 0 && <EmptyState icon={<MapIcon className="h-8 w-8" />} title={t("dashboard.empty_title")} text={t("dashboard.empty_text")} action={add} />}
      {!!fields.data?.length && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {fields.data.map((f) => (
            <Link key={f.id} to={`/app/fields/${f.id}`} className="panel group flex flex-col p-4 no-underline hover:border-field-300">
              <div className="flex items-start gap-3">
                <FieldThumb geometry={f.geometry} size={52} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold text-ink">{f.name}</div>
                  <div className="text-sm text-ink-muted">
                    {tx(config?.regions.find((r) => r.id === f.region)?.name, lang) || f.region} · {fmtNum(f.area_ha, 1)} {t("units.ha")}
                  </div>
                </div>
                <ArrowRight className="h-4 w-4 text-ink-subtle group-hover:text-field-700" />
              </div>
              <div className="mt-4 flex flex-wrap gap-1">
                {f.history.slice(-5).map((h) => (
                  <span key={h.year} className="badge-neutral" title={String(h.year)}>
                    {h.year % 100 < 10 ? `0${h.year % 100}` : h.year % 100}′ {cropName(h.crop, lang)}
                  </span>
                ))}
                {f.history_is_scenario && <span className="badge-amber">{t("fields.scenario_badge")}</span>}
              </div>
              <div className="mt-4 flex justify-between border-t border-line pt-3 text-xs text-ink-muted">
                <span>{t("fields.n_analyses", { count: f.n_analyses ?? 0 })}</span>
                <span>{t("fields.updated", { date: fmtDate(f.updated_at, lang) })}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
