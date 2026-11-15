import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Area, Bar, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../api/client";
import type { SeasonRow } from "../../api/types";
import { errorText, useAsync } from "../../lib/async";
import { SERIES } from "../../lib/colors";
import { fmtNum } from "../../lib/format";
import ChartFrame, { AXIS, C, GRID, TooltipBox } from "../charts/ChartFrame";
import { ErrorBox, KindBadge, Loading, Notice, SectionTitle } from "../ui/ui";

const DOY_MONTH = (doy: number) => {
  const d = new Date(Date.UTC(2021, 0, doy));
  return `${String(d.getUTCDate()).padStart(2, "0")}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};

export default function History({ fieldId }: { fieldId: number }) {
  const { t } = useTranslation();
  const s = useAsync(() => api.fieldSeasons(fieldId), [fieldId]);
  const [picked, setPicked] = useState<string[] | null>(null);
  const data = s.data;

  const curveYears = useMemo(() => Object.keys(data?.ndvi_curves ?? {}).sort(), [data]);
  const chosen = picked ?? [...(curveYears.includes("2021") ? ["2021"] : []), ...curveYears.slice(-1)].filter((v, i, a) => a.indexOf(v) === i);
  const curveRows = useMemo(() => {
    if (!data) return [];
    const byDoy = new Map<number, Record<string, number | number[] | null>>();
    for (const c of data.ndvi_climatology) byDoy.set(c.doy, { doy: c.doy, median: c.median, band: [c.p10, c.p90] });
    for (const y of chosen) {
      for (const p of data.ndvi_curves[y] ?? []) {
        const row = byDoy.get(p.doy) ?? { doy: p.doy };
        row[`y${y}`] = p.ndvi;
        byDoy.set(p.doy, row);
      }
    }
    return [...byDoy.values()].sort((a, b) => Number(a.doy) - Number(b.doy));
  }, [data, chosen]);

  if (s.error) return <ErrorBox message={errorText(s.error, t)} onRetry={s.reload} />;
  if (!data) return <Loading />;

  const years = data.years;
  const b = data.baseline;
  const trend = data.ndvi_trend;
  const trendRows = years.map((y) => ({
    ...y,
    trend: trend?.slope_per_year != null && trend.intercept != null && trend.from_year != null && y.year >= trend.from_year ? trend.intercept + trend.slope_per_year * y.year : null,
  }));
  const yLabel = (r: SeasonRow) => String(r.year);
  const togglePick = (y: string) => {
    const cur = new Set(chosen);
    if (cur.has(y)) cur.delete(y);
    else if (cur.size < 4) cur.add(y);
    setPicked([...cur].sort());
  };

  return (
    <div className="space-y-6">
      <Notice tone="warn">{t("history.caveat")}</Notice>

      <div className="grid gap-6 xl:grid-cols-2">
        <ChartFrame
          title={t("history.precip_title")}
          legend={[{ color: C.precip, label: t("result.summary.precip_chart_normal") }, { color: C.dry, label: t("result.summary.precip_chart_dry") }, { color: C.normal, label: t("history.baseline_mean", { from: b.years[0], to: b.years[1] }), dashed: true }]}
          caption={<><KindBadge kind="reanalysis" /> NASA POWER · {t("history.precip_caption")}</>}
          table={{ columns: [t("history.year"), t("units.mm"), "z", t("history.dry")], rows: years.map((y) => [y.year, fmtNum(y.precip_mm, 0), fmtNum(y.precip_anomaly_z, 2), y.is_dry ? t("history.yes") : ""]) }}
        >
          <ResponsiveContainer>
            <ComposedChart data={years} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="year" tick={AXIS} minTickGap={8} />
              <YAxis tick={AXIS} />
              <ReferenceLine y={b.precip_mean} stroke={C.normal} strokeDasharray="4 3" />
              <Tooltip content={({ active, payload }) => {
                const r = active ? (payload?.[0]?.payload as SeasonRow | undefined) : undefined;
                return r ? <TooltipBox title={yLabel(r)} rows={[{ label: t("history.precip_may_aug"), value: `${fmtNum(r.precip_mm, 0)} ${t("units.mm")}` }, { label: "z", value: fmtNum(r.precip_anomaly_z, 2) }, ...(r.is_dry ? [{ label: t("history.dry"), value: t("history.yes") }] : [])]} /> : null;
              }} />
              <Bar dataKey="precip_mm" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                {years.map((y) => <Cell key={y.year} fill={y.is_dry ? C.dry : C.precip} />)}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        </ChartFrame>

        <ChartFrame
          title={t("history.temp_title")}
          legend={[{ color: C.warm, label: t("monitoring.warmer") }, { color: C.cool, label: t("monitoring.colder") }]}
          caption={<><KindBadge kind="reanalysis" /> NASA POWER · {t("history.temp_caption", { from: b.years[0], to: b.years[1], t: fmtNum(b.t_mean, 1), threshold: data.hot_day_threshold_c })}</>}
          table={{ columns: [t("history.year"), "°C", "Δ °C", t("monitoring.hot_days")], rows: years.map((y) => [y.year, fmtNum(y.t_mean, 1), fmtNum(y.t_anomaly, 1), y.hot_days]) }}
        >
          <ResponsiveContainer>
            <ComposedChart data={years} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="year" tick={AXIS} minTickGap={8} />
              <YAxis tick={AXIS} unit="°" />
              <ReferenceLine y={0} stroke="#8A929C" />
              <Tooltip content={({ active, payload }) => {
                const r = active ? (payload?.[0]?.payload as SeasonRow | undefined) : undefined;
                return r ? <TooltipBox title={yLabel(r)} rows={[{ label: t("monitoring.t_mean"), value: `${fmtNum(r.t_mean, 1)} °C` }, { label: t("monitoring.anomaly"), value: `${fmtNum(r.t_anomaly, 1)} °C` }, { label: t("monitoring.hot_days"), value: String(r.hot_days ?? "—") }]} /> : null;
              }} />
              <Bar dataKey="t_anomaly" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                {years.map((y) => <Cell key={y.year} fill={(y.t_anomaly ?? 0) >= 0 ? C.warm : C.cool} />)}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        </ChartFrame>

        <ChartFrame
          title={t("history.ndvi_title")}
          legend={[{ color: C.ndvi, label: t("history.ndvi_max") }, { color: C.normal, label: t("result.summary.ndvi_chart_trend"), dashed: true }]}
          caption={<><KindBadge kind="observation" /> MODIS MOD13Q1 · {trend ? t("history.trend_caption", { label: t(`result.summary.ndvi_${trend.label}`), slope: fmtNum(trend.slope_per_year, 4), p: fmtNum(trend.p_value, 3), from: trend.from_year ?? "", to: trend.to_year ?? "" }) : t("monitoring.no_ndvi")}</>}
          table={{ columns: [t("history.year"), t("history.ndvi_max"), t("history.ndvi_date"), t("history.ndvi_mean"), t("history.n_composites")], rows: years.map((y) => [y.year, fmtNum(y.ndvi_max, 3), y.ndvi_max_date, fmtNum(y.ndvi_mean, 3), y.n_composites]) }}
        >
          <ResponsiveContainer>
            <ComposedChart data={trendRows.filter((y) => y.ndvi_max !== null)} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="year" tick={AXIS} minTickGap={8} />
              <YAxis tick={AXIS} domain={["auto", "auto"]} />
              <Tooltip content={({ active, payload }) => {
                const r = active ? (payload?.[0]?.payload as SeasonRow | undefined) : undefined;
                return r ? <TooltipBox title={yLabel(r)} rows={[{ label: t("history.ndvi_max"), value: fmtNum(r.ndvi_max, 3), color: C.ndvi }, { label: t("history.ndvi_date"), value: r.ndvi_max_date ?? "—" }]} /> : null;
              }} />
              <Line dataKey="trend" stroke={C.normal} strokeDasharray="4 3" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line dataKey="ndvi_max" stroke={C.ndvi} strokeWidth={2} dot={{ r: 3.5, fill: "#fff", strokeWidth: 2 }} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartFrame>

        <ChartFrame
          title={t("history.curves_title")}
          legend={[...chosen.map((y, i) => ({ color: SERIES[i] ?? "#2a78d6", label: y })), { color: C.normal, label: t("monitoring.ndvi_median"), dashed: true }, { color: C.band, label: t("monitoring.ndvi_band"), band: true }]}
          caption={t("history.curves_caption")}
        >
          <div className="flex h-full flex-col">
            <div className="mb-2 flex flex-wrap gap-1">
              {curveYears.map((y) => (
                <button key={y} type="button" aria-pressed={chosen.includes(y)} onClick={() => togglePick(y)} className={`h-6 rounded px-1.5 text-xs font-medium ${chosen.includes(y) ? "bg-field-700 text-white" : "bg-surface-sunken text-ink-2 hover:text-ink"}`}>
                  {y}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1">
              <ResponsiveContainer>
                <ComposedChart data={curveRows} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="doy" type="number" domain={["dataMin", "dataMax"]} tick={AXIS} tickFormatter={DOY_MONTH} />
                  <YAxis tick={AXIS} domain={[0, 1]} />
                  <Tooltip labelFormatter={(d: number) => DOY_MONTH(d)} formatter={(v: number | number[], k: string) => [Array.isArray(v) ? v.map((x) => fmtNum(x, 2)).join("–") : fmtNum(v, 3), k.startsWith("y") ? k.slice(1) : k === "band" ? "P10–P90" : t("monitoring.ndvi_median")]} />
                  <Area dataKey="band" stroke="none" fill={C.band} fillOpacity={0.7} isAnimationActive={false} connectNulls />
                  <Line dataKey="median" stroke={C.normal} strokeDasharray="4 3" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
                  {chosen.map((y, i) => (
                    <Line key={y} dataKey={`y${y}`} stroke={SERIES[i] ?? "#2a78d6"} strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} connectNulls />
                  ))}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        </ChartFrame>
      </div>

      <section>
        <SectionTitle title={t("history.table_title")} hint={t("history.table_hint")} />
        <div className="panel overflow-x-auto">
          <table className="table min-w-[900px]">
            <thead>
              <tr>
                <th>{t("history.year")}</th>
                <th className="num">{t("history.precip_may_aug")}</th>
                <th className="num">z</th>
                <th className="num">{t("monitoring.t_mean")}</th>
                <th className="num">Δ °C</th>
                <th className="num">{t("monitoring.hot_days")}</th>
                <th className="num">{t("history.ndvi_max")}</th>
                <th className="num">{t("history.ndvi_mean")}</th>
                <th className="num">{t("history.smap_spring")}</th>
                <th className="num">{t("history.gwet_spring")}</th>
              </tr>
            </thead>
            <tbody>
              {[...years].reverse().map((y) => (
                <tr key={y.year} className={y.is_dry ? "bg-orange-50/60" : ""}>
                  <td className="font-medium">
                    {y.year} {y.is_dry && <span className="badge-amber ml-1">{t("history.dry")}</span>}
                  </td>
                  <td className="num">{fmtNum(y.precip_mm, 0)}</td>
                  <td className="num">{fmtNum(y.precip_anomaly_z, 2)}</td>
                  <td className="num">{fmtNum(y.t_mean, 1)}</td>
                  <td className="num">{fmtNum(y.t_anomaly, 1)}</td>
                  <td className="num">{y.hot_days ?? "—"}</td>
                  <td className="num">{fmtNum(y.ndvi_max, 3)}</td>
                  <td className="num">{fmtNum(y.ndvi_mean, 3)}</td>
                  <td className="num">{fmtNum(y.smap_spring, 3)}</td>
                  <td className="num">{fmtNum(y.gwet_spring, 2)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-line-strong font-medium">
                <td>{t("history.average")}</td>
                <td className="num">{fmtNum(data.window_averages.precip_mm, 0)}</td>
                <td />
                <td className="num">{fmtNum(data.window_averages.t_mean, 1)}</td>
                <td />
                <td className="num">{fmtNum(data.window_averages.hot_days, 1)}</td>
                <td className="num">{fmtNum(data.window_averages.ndvi_max, 3)}</td>
                <td className="num">{fmtNum(data.window_averages.ndvi_mean, 3)}</td>
                <td className="num">{fmtNum(data.window_averages.smap_spring, 3)}</td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      </section>
    </div>
  );
}
