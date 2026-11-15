import { useTranslation } from "react-i18next";
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { Analysis, Lang } from "../../api/types";
import { fmtNum } from "../../lib/format";

const DRY = "#eb6834";
const NORMAL = "#2a78d6";

function Stat({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="text-2xl font-semibold text-field-800">{value}</div>
      {detail && <div className="mt-1 text-sm text-ink-2">{detail}</div>}
    </div>
  );
}

export function Warnings({ analysis }: { analysis: Analysis }) {
  const { t } = useTranslation();
  const seen = new Set<string>();
  const items = analysis.warnings.filter((w) => {
    const k = `${w.code}:${w.source}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  if (!items.length) return null;
  return (
    <section className="card border-amber-400 bg-amber-50">
      <h3 className="h3 mb-2">{t("warnings.title")}</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm text-amber-950">
        {items.map((w) => (
          <li key={`${w.code}-${w.source}`}>
            {t(`warnings.${w.code}`, {
              source: w.source,
              detail: String(w.params.detail ?? ""),
              pixels: w.params.pixels,
              years: Array.isArray(w.params.years) ? (w.params.years as number[]).join(", ") : "",
              humus_pct: fmtNum(Number(w.params.humus_pct ?? 0), 1),
              defaultValue: w.code,
            })}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function DataSummary({ analysis }: { analysis: Analysis }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const d = analysis.drought;
  const w = d.window;
  const trend = analysis.ndvi.trend;
  const soil = analysis.soil.summary;
  const stock = analysis.soil_moisture.stock;
  const origin = (o: string | null | undefined) => (o ? t(`result.summary.origin.${o}`) : "");

  const precipRows = d.years.filter((y) => y.year >= (w?.from ?? 0)).map((y) => ({ year: y.year, precip: y.precip_mm, dry: y.is_dry }));
  const ndviRows =
    trend?.yearly_max.map((r) => ({
      year: r.year,
      ndvi: r.ndvi,
      fit: trend.slope_per_year !== null && trend.intercept !== undefined ? trend.intercept + trend.slope_per_year * r.year : null,
    })) ?? [];

  let ndviValue = t("result.summary.ndvi_unavailable");
  if (trend) ndviValue = t(`result.summary.ndvi_${trend.label}`);
  else if (analysis.ndvi.state.status === "pending") ndviValue = t("result.summary.ndvi_pending");

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label={t("result.summary.area")}
          value={`${fmtNum(analysis.field.area_ha, 1)} ${t("wizard.field.ha")}`}
          detail={`${analysis.field.region_name[lang]} · ${analysis.field.centroid.lat.toFixed(4)}, ${analysis.field.centroid.lon.toFixed(4)}`}
        />
        <Stat
          label={t("result.summary.dry_years")}
          value={d.every_nth ? t("result.summary.dry_phrase", { n: d.every_nth }) : t("result.summary.dry_phrase_none")}
          detail={w ? t("result.summary.dry_detail", { count: d.dry_years.length, total: w.n_years, from: w.from, to: w.to, years: d.dry_years.join(", ") }) : undefined}
        />
        <Stat
          label={t("result.summary.ndvi")}
          value={ndviValue}
          detail={
            trend && trend.label !== "insufficient"
              ? t("result.summary.ndvi_detail", {
                  from: trend.from_year,
                  to: trend.to_year,
                  slope: fmtNum(trend.slope_per_year ?? 0, 4),
                  p: fmtNum(trend.p_value ?? 0, 3),
                })
              : undefined
          }
        />
        <Stat
          label={t("result.summary.stock")}
          value={`${fmtNum(stock.normal_stock_mm, 0)} ${t("units.mm")}`}
          detail={`${t(stock.uses_smap ? "result.summary.stock_smap" : "result.summary.stock_power")}${soil ? ` · ${t("result.summary.awc", { awc: fmtNum(soil.awc_mm, 0) })}` : ""}`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <figure className="card">
          <figcaption className="h3">{t("result.summary.precip_chart")}</figcaption>
          <p className="muted mb-2">
            {t("result.summary.normal_precip")}: <b>{fmtNum(analysis.climate.normal_precip_mm, 0)} {t("units.mm")}</b> · NASA POWER, {origin(analysis.climate.origin)}
          </p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={precipRows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#E3E6EA" vertical={false} />
                <XAxis dataKey="year" tick={{ fontSize: 12 }} interval={3} />
                <YAxis tick={{ fontSize: 12 }} width={40} />
                <ReferenceLine y={d.definition.percentile_mm} stroke={DRY} strokeDasharray="4 4" />
                <Tooltip formatter={(v: number) => [`${fmtNum(v, 0)} ${t("units.mm")}`, ""]} />
                <Bar dataKey="precip" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                  {precipRows.map((r) => (
                    <Cell key={r.year} fill={r.dry ? DRY : NORMAL} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-1 flex gap-4 text-sm">
            <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: NORMAL }} />{t("result.summary.precip_chart_normal")}</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: DRY }} />{t("result.summary.precip_chart_dry")}</span>
          </div>
          <p className="mt-2 text-xs text-ink-muted">
            {t("result.summary.dry_definition", {
              p: fmtNum(d.definition.percentile_mm, 0),
              b0: d.definition.baseline[0],
              b1: d.definition.baseline[1],
              mean: fmtNum(d.definition.baseline_mean_mm, 0),
              std: fmtNum(d.definition.baseline_std_mm, 0),
            })}
          </p>
        </figure>

        <figure className="card">
          <figcaption className="h3">{t("result.summary.ndvi_chart")}</figcaption>
          <p className="muted mb-2">
            MODIS MOD13Q1 · {analysis.ndvi.n_field_pixels ?? "—"} px · {origin(analysis.ndvi.origin)}
          </p>
          {ndviRows.length ? (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={ndviRows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#E3E6EA" vertical={false} />
                  <XAxis dataKey="year" tick={{ fontSize: 12 }} interval={3} type="number" domain={["dataMin", "dataMax"]} />
                  <YAxis tick={{ fontSize: 12 }} width={40} domain={[0, 1]} />
                  <Tooltip formatter={(v: number, k: string) => [fmtNum(v, 3), k === "fit" ? t("result.summary.ndvi_chart_trend") : "NDVI"]} />
                  <Legend formatter={(k: string) => (k === "fit" ? t("result.summary.ndvi_chart_trend") : "NDVI max")} wrapperStyle={{ fontSize: 12 }} />
                  <Scatter dataKey="ndvi" fill="#1baf7a" isAnimationActive={false} />
                  <Line dataKey="fit" stroke="#52514e" strokeDasharray="5 4" dot={false} strokeWidth={2} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-ink-2">{ndviValue}</p>
          )}
        </figure>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card">
          <div className="label">{t("result.summary.soil")}</div>
          {soil ? (
            <p>
              {t("result.summary.soil_detail", {
                humus: fmtNum(soil.topsoil.humus_pct, 1),
                clay: fmtNum(soil.topsoil.clay_pct, 0),
                sand: fmtNum(soil.topsoil.sand_pct, 0),
                ph: fmtNum(soil.topsoil.ph, 1),
              })}{" "}
              <span className="text-sm text-ink-muted">({origin(analysis.soil.origin)})</span>
            </p>
          ) : (
            <p>{t("result.summary.soil_unavailable")}</p>
          )}
        </div>
        <div className="card">
          <div className="label">{t("result.summary.stress_year", { year: d.stress_year, precip: fmtNum(d.years.find((y) => y.year === d.stress_year)?.precip_mm ?? 0, 0) })}</div>
          <p className="text-sm">{t(d.stress_year_reason === "default_year" ? "result.summary.stress_reason_default" : "result.summary.stress_reason_driest")}</p>
        </div>
      </div>
    </div>
  );
}
