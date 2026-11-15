import { useTranslation } from "react-i18next";
import type { Analysis, FieldRecord, Lang } from "../../api/types";
import { useCropName } from "../../lib/config";
import { fmtInt, fmtNum } from "../../lib/format";
import { tx } from "../../lib/i18n-text";
import { Warnings } from "../results/DataSummary";
import { KindBadge, Loading, Notice, SectionTitle, Stat } from "../ui/ui";

export default function Overview({ field, overview, error }: { field: FieldRecord; overview: Analysis | null; error: string | null }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const cropName = useCropName();
  const a = overview;
  const top = a?.soil.summary?.topsoil;
  const userSoil = field.soil;
  const trend = a?.ndvi.trend;
  return (
    <div className="space-y-8">
      {error && <Notice tone="warn">{error}</Notice>}
      {!a && !error && <Loading label={t("result.calculating")} />}
      {a && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label={t("result.summary.normal_precip")} value={`${fmtInt(a.conditions.p_season_normal)} ${t("units.mm")}`} hint={t("overview.precip_hint", { from: a.drought.window?.from ?? a.climate.series_from, to: a.drought.window?.to ?? "" })} />
          <Stat label={t("result.summary.stock")} value={`${fmtInt(a.conditions.stock_normal)} ${t("units.mm")}`} hint={t(a.conditions.moisture_basis === "smap" ? "result.summary.stock_smap" : "result.summary.stock_power")} />
          <Stat
            label={t("result.summary.dry_years")}
            value={a.drought.every_nth ? t("result.summary.dry_phrase", { n: a.drought.every_nth }) : t("result.summary.dry_phrase_none")}
            hint={a.drought.dry_years.join(", ")}
            tone={a.drought.every_nth && a.drought.every_nth <= 4 ? "warn" : "default"}
          />
          <Stat
            label={t("result.summary.ndvi")}
            value={trend ? t(`result.summary.ndvi_${trend.label}`) : a.ndvi.state.status === "pending" ? t("result.summary.ndvi_pending") : t("result.summary.ndvi_unavailable")}
            hint={trend && trend.from_year ? t("overview.ndvi_hint", { from: trend.from_year, to: trend.to_year, p: fmtNum(trend.p_value, 3) }) : undefined}
          />
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="panel">
          <div className="panel-head"><h2 className="h3">{t("overview.field_title")}</h2></div>
          <div className="panel-body space-y-4 text-sm">
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2">
              <dt className="text-ink-muted">{t("result.summary.area")}</dt>
              <dd className="tabular-nums">{fmtNum(field.area_ha, 1)} {t("units.ha")}</dd>
              <dt className="text-ink-muted">{t("overview.centroid")}</dt>
              <dd className="tabular-nums">{fmtNum(field.centroid_lat, 4)}° N, {fmtNum(field.centroid_lon, 4)}° E</dd>
              {a?.climate.elevation_m != null && (
                <>
                  <dt className="text-ink-muted">{t("overview.elevation")}</dt>
                  <dd className="tabular-nums">{fmtInt(a.climate.elevation_m)} m</dd>
                </>
              )}
              <dt className="text-ink-muted">{t("fields.history")}</dt>
              <dd className="flex flex-wrap gap-1">
                {field.history.map((h) => <span key={h.year} className="badge-neutral">{h.year}: {cropName(h.crop, lang)}</span>)}
                {field.history_is_scenario && <span className="badge-amber">{t("fields.scenario_badge")}</span>}
              </dd>
            </dl>
            {field.notes && <p className="whitespace-pre-line rounded-md bg-surface px-3 py-2 text-ink-2">{field.notes}</p>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><h2 className="h3">{t("overview.soil_title")}</h2></div>
          <div className="panel-body space-y-3">
            <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th />
                  <th className="num">{t("overview.soil_user")}</th>
                  <th className="num">
                    <span className="inline-flex items-center gap-1.5">SoilGrids 0–30 {t("overview.cm")} <KindBadge kind="model" /></span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr><td>{t("fields.humus")}</td><td className="num">{fmtNum(userSoil.humus_pct, 1)}</td><td className="num">{fmtNum(top?.humus_pct, 1)}</td></tr>
                <tr><td>pH</td><td className="num">{fmtNum(userSoil.ph, 1)}</td><td className="num">{fmtNum(top?.ph, 1)}</td></tr>
                <tr><td>{t("fields.texture")}</td><td className="num">{userSoil.texture ? t(`fields.textures.${userSoil.texture}`) : "—"}</td><td className="num">{a?.soil.summary?.texture_class ?? "—"}</td></tr>
                <tr><td>{t("overview.clay_sand")}</td><td className="num">—</td><td className="num">{fmtNum(top?.clay_pct, 0)} / {fmtNum(top?.sand_pct, 0)}</td></tr>
                <tr><td>{t("overview.awc")}</td><td className="num">—</td><td className="num">{a?.soil.summary ? `${fmtInt(a.soil.summary.awc_mm)} ${t("units.mm")}` : "—"}</td></tr>
              </tbody>
            </table>
            </div>
            <p className="text-xs text-ink-muted">{t("overview.soil_note")}{userSoil.survey_year ? ` ${t("overview.survey", { year: userSoil.survey_year })}` : ""}</p>
          </div>
        </section>
      </div>

      {a && (
        <section>
          <SectionTitle title={t("overview.resolution_title")} hint={t("overview.resolution_hint")} />
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {a.resolutions.map((r) => (
              <div key={r.source} className="panel p-4 text-sm">
                <div className="font-medium text-ink">{r.title}</div>
                <p className="mt-1 text-xs leading-relaxed text-ink-muted">{tx(r.spatial_resolution, lang)}</p>
                <p className="mt-2 text-xs text-ink-2">{tx(r.temporal_coverage, lang)}</p>
              </div>
            ))}
          </div>
        </section>
      )}
      {a && <Warnings analysis={a} />}
    </div>
  );
}
