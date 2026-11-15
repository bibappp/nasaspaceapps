import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Area, Bar, CartesianGrid, Cell, ComposedChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../api/client";
import type { Monitoring as MonitoringData } from "../../api/types";
import { errorText, useAsync } from "../../lib/async";
import { fmtNum } from "../../lib/format";
import ChartFrame, { AXIS, C, GRID, TooltipBox } from "../charts/ChartFrame";
import { ErrorBox, KindBadge, Loading, Notice, SectionTitle, Stat } from "../ui/ui";
import SourceList from "./SourceList";

type Layer = "precip" | "temperature" | "ndvi" | "moisture";
const LAYERS: Layer[] = ["precip", "temperature", "ndvi", "moisture"];

function monthsAgo(end: string, n: number): string {
  const [y = 2000, m = 1] = end.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 - n, 1));
  return d.toISOString().slice(0, 7);
}

function sum(xs: (number | null)[]): number | null {
  const v = xs.filter((x): x is number => x !== null);
  return v.length ? v.reduce((a, b) => a + b, 0) : null;
}
function mean(xs: (number | null)[]): number | null {
  const v = xs.filter((x): x is number => x !== null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

function useJobsPolling(data: MonitoringData | null, reload: () => void) {
  const pending = (data?.jobs ?? []).filter((j) => j.status === "pending" && j.job);
  const key = pending.map((j) => j.job?.id).join("|");
  useEffect(() => {
    if (!pending.length) return;
    const timer = window.setInterval(() => {
      void Promise.all(pending.map((j) => api.job(j.job!.id).catch(() => null))).then((js) => {
        if (js.some((j) => !j || j.status !== "running")) reload();
      });
    }, 4000);
    return () => window.clearInterval(timer);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return pending;
}

export default function Monitoring({ fieldId }: { fieldId: number }) {
  const { t } = useTranslation();
  const [range, setRange] = useState<{ start?: string; end?: string }>({});
  const [layers, setLayers] = useState<Set<Layer>>(new Set(LAYERS));
  const mon = useAsync(() => api.fieldMonitoring(fieldId, range.start, range.end), [fieldId, range.start, range.end]);
  const pending = useJobsPolling(mon.data, mon.reload);
  const d = mon.data;

  const months = d?.climate.months ?? [];
  const summary = useMemo(() => {
    const p = sum(months.map((m) => m.precip_mm));
    const pn = sum(months.map((m) => (m.precip_mm === null ? null : m.precip_normal_mm)));
    const last = d?.ndvi.composites.filter((c) => c.ndvi !== null).at(-1);
    return {
      precip: p,
      precipPct: p !== null && pn ? (p / pn) * 100 : null,
      tAnom: mean(months.map((m) => m.t_anomaly)),
      hot: sum(months.map((m) => m.hot_days)),
      ndvi: last,
      sm: mean((d?.soil_moisture.days ?? []).map((x) => x.sm)),
    };
  }, [d, months]);

  if (mon.error) return <ErrorBox message={errorText(mon.error, t)} onRetry={mon.reload} />;
  if (!d) return <Loading />;

  const avail = d.climate.available;
  const toggle = (l: Layer) => setLayers((s) => {
    const n = new Set(s);
    if (n.has(l)) n.delete(l);
    else n.add(l);
    return n;
  });
  const preset = (n: number | "all") => setRange(n === "all" ? { start: avail[0], end: avail[1] } : { start: monthsAgo(avail[1], n - 1), end: avail[1] });
  const tick = (m: string) => `${m.slice(5)}.${m.slice(2, 4)}`;
  const baseline = `${d.climate.baseline[0]}–${d.climate.baseline[1]}`;

  return (
    <div className="space-y-6">
      <div className="panel">
        <div className="panel-body flex flex-wrap items-end gap-4">
          <label className="block">
            <span className="label">{t("monitoring.from")}</span>
            <input type="month" className="input w-40" min={avail[0]} max={avail[1]} value={d.range.start} onChange={(e) => e.target.value && setRange({ ...range, start: e.target.value, end: d.range.end })} />
          </label>
          <label className="block">
            <span className="label">{t("monitoring.to")}</span>
            <input type="month" className="input w-40" min={avail[0]} max={avail[1]} value={d.range.end} onChange={(e) => e.target.value && setRange({ ...range, end: e.target.value, start: d.range.start })} />
          </label>
          <div className="flex flex-wrap gap-1.5">
            {([12, 36, 60, "all"] as const).map((n) => (
              <button key={n} type="button" className="btn-secondary h-9" onClick={() => preset(n)}>
                {n === "all" ? t("monitoring.all") : t("monitoring.last_months", { count: n })}
              </button>
            ))}
          </div>
          <div className="flex-1" />
          <fieldset className="flex flex-wrap gap-1.5">
            <legend className="label">{t("monitoring.layers")}</legend>
            {LAYERS.map((l) => (
              <button key={l} type="button" aria-pressed={layers.has(l)} onClick={() => toggle(l)} className={layers.has(l) ? "btn-primary h-8 px-2.5 text-xs" : "btn-secondary h-8 px-2.5 text-xs"}>
                {t(`monitoring.layer.${l}`)}
              </button>
            ))}
          </fieldset>
        </div>
      </div>

      {mon.loading && <Loading />}
      {pending.length > 0 && (
        <Notice>{t("monitoring.pending", { sources: pending.map((j) => j.source.toUpperCase()).join(", ") })}</Notice>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Stat label={t("monitoring.stat_precip")} value={summary.precip === null ? "—" : `${fmtNum(summary.precip, 0)} ${t("units.mm")}`} hint={summary.precipPct === null ? undefined : t("monitoring.pct_of_normal", { pct: fmtNum(summary.precipPct, 0), baseline })} />
        <Stat label={t("monitoring.stat_tanom")} value={summary.tAnom === null ? "—" : `${summary.tAnom > 0 ? "+" : ""}${fmtNum(summary.tAnom, 1)} °C`} hint={t("monitoring.vs_baseline", { baseline })} tone={summary.tAnom !== null && summary.tAnom >= 1 ? "warn" : "default"} />
        <Stat label={t("monitoring.stat_hot", { threshold: d.hot_day_threshold_c })} value={summary.hot ?? "—"} hint={t("monitoring.days_in_range")} />
        <Stat label={t("monitoring.stat_ndvi")} value={summary.ndvi ? fmtNum(summary.ndvi.ndvi, 2) : "—"} hint={summary.ndvi ? t("monitoring.ndvi_hint", { date: summary.ndvi.date, median: fmtNum(summary.ndvi.median, 2) }) : t("monitoring.no_ndvi")} />
        <Stat label={t("monitoring.stat_sm")} value={summary.sm === null ? "—" : `${fmtNum(summary.sm, 3)}`} hint={summary.sm === null ? t("monitoring.no_smap") : t("monitoring.sm_hint")} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        {layers.has("precip") && (
          <ChartFrame
            title={t("monitoring.precip_title")}
            legend={[{ color: C.precip, label: t("monitoring.precip_obs") }, { color: C.normal, label: t("monitoring.normal", { baseline }), dashed: true }]}
            caption={<><KindBadge kind="reanalysis" /> {d.sources.power.title} · {t("monitoring.power_caption")}</>}
            table={{ columns: [t("monitoring.month"), t("units.mm"), t("monitoring.normal_short"), "%"], rows: months.map((m) => [m.month, fmtNum(m.precip_mm, 1), fmtNum(m.precip_normal_mm, 1), fmtNum(m.precip_pct_of_normal, 0)]) }}
          >
            <ResponsiveContainer>
              <ComposedChart data={months} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="month" tick={AXIS} tickFormatter={tick} minTickGap={18} />
                <YAxis tick={AXIS} />
                <Tooltip content={({ active, payload }) => {
                  const m = active ? (payload?.[0]?.payload as (typeof months)[number] | undefined) : undefined;
                  return m ? <TooltipBox title={m.month} rows={[{ label: t("monitoring.precip_obs"), value: `${fmtNum(m.precip_mm, 1)} ${t("units.mm")}`, color: C.precip }, { label: t("monitoring.normal_short"), value: `${fmtNum(m.precip_normal_mm, 1)} ${t("units.mm")}`, color: C.normal }, { label: "%", value: fmtNum(m.precip_pct_of_normal, 0) }]} /> : null;
                }} />
                <Bar dataKey="precip_mm" fill={C.precip} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                <Line dataKey="precip_normal_mm" stroke={C.normal} strokeDasharray="4 3" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartFrame>
        )}

        {layers.has("temperature") && (
          <ChartFrame
            title={t("monitoring.temp_title")}
            legend={[{ color: C.warm, label: t("monitoring.warmer") }, { color: C.cool, label: t("monitoring.colder") }]}
            caption={<><KindBadge kind="reanalysis" /> {d.sources.power.title} · {t("monitoring.temp_caption", { baseline })}</>}
            table={{ columns: [t("monitoring.month"), "°C", t("monitoring.normal_short"), "Δ °C", t("monitoring.hot_days")], rows: months.map((m) => [m.month, fmtNum(m.t_mean, 1), fmtNum(m.t_normal, 1), fmtNum(m.t_anomaly, 1), m.hot_days]) }}
          >
            <ResponsiveContainer>
              <ComposedChart data={months} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="month" tick={AXIS} tickFormatter={tick} minTickGap={18} />
                <YAxis tick={AXIS} unit="°" />
                <ReferenceLine y={0} stroke="#8A929C" />
                <Tooltip content={({ active, payload }) => {
                  const m = active ? (payload?.[0]?.payload as (typeof months)[number] | undefined) : undefined;
                  return m ? <TooltipBox title={m.month} rows={[{ label: t("monitoring.t_mean"), value: `${fmtNum(m.t_mean, 1)} °C` }, { label: t("monitoring.normal_short"), value: `${fmtNum(m.t_normal, 1)} °C` }, { label: t("monitoring.anomaly"), value: `${fmtNum(m.t_anomaly, 1)} °C` }, { label: t("monitoring.hot_days"), value: String(m.hot_days) }]} /> : null;
                }} />
                <Bar dataKey="t_anomaly" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                  {months.map((m) => <Cell key={m.month} fill={(m.t_anomaly ?? 0) >= 0 ? C.warm : C.cool} />)}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
          </ChartFrame>
        )}

        {layers.has("ndvi") && (
          <ChartFrame
            title={t("monitoring.ndvi_title")}
            legend={[{ color: C.ndvi, label: t("monitoring.ndvi_field") }, { color: C.normal, label: t("monitoring.ndvi_median"), dashed: true }, { color: C.band, label: t("monitoring.ndvi_band"), band: true }]}
            caption={<><KindBadge kind="observation" /> {d.sources.modis.title} · {t("monitoring.ndvi_caption", { n: d.ndvi.n_field_pixels ?? "—" })}</>}
            table={{ columns: [t("monitoring.date"), "NDVI", t("monitoring.ndvi_median"), "P10", "P90", t("monitoring.valid")], rows: d.ndvi.composites.map((c) => [c.date, fmtNum(c.ndvi, 3), fmtNum(c.median, 3), fmtNum(c.p10, 3), fmtNum(c.p90, 3), `${fmtNum(c.valid_fraction * 100, 0)} %`]) }}
          >
            {d.ndvi.available && d.ndvi.composites.length ? (
              <ResponsiveContainer>
                <ComposedChart data={d.ndvi.composites.map((c) => ({ ...c, band: c.p10 !== null && c.p90 !== null ? [c.p10, c.p90] : null }))} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="date" tick={AXIS} tickFormatter={(x: string) => x.slice(0, 7)} minTickGap={24} />
                  <YAxis tick={AXIS} domain={[0, 1]} />
                  <Tooltip content={({ active, payload }) => {
                    const c = active ? (payload?.[0]?.payload as MonitoringData["ndvi"]["composites"][number] | undefined) : undefined;
                    return c ? <TooltipBox title={c.date} rows={[{ label: t("monitoring.ndvi_field"), value: fmtNum(c.ndvi, 3), color: C.ndvi }, { label: t("monitoring.ndvi_median"), value: fmtNum(c.median, 3) }, { label: "P10–P90", value: `${fmtNum(c.p10, 2)}–${fmtNum(c.p90, 2)}` }, { label: t("monitoring.anomaly"), value: fmtNum(c.anomaly, 3) }]} /> : null;
                  }} />
                  <Area dataKey="band" stroke="none" fill={C.band} fillOpacity={0.7} isAnimationActive={false} connectNulls />
                  <Line dataKey="median" stroke={C.normal} strokeDasharray="4 3" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
                  <Line dataKey="ndvi" stroke={C.ndvi} strokeWidth={2} dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <Notice>{t("monitoring.no_ndvi")}</Notice>
            )}
          </ChartFrame>
        )}

        {layers.has("moisture") && (
          <ChartFrame
            title={t("monitoring.sm_title")}
            caption={<><KindBadge kind="observation" /> {d.sources.smap.title} · {t("monitoring.sm_caption")}</>}
            table={{ columns: [t("monitoring.date"), t("units.m3m3")], rows: d.soil_moisture.days.map((x) => [x.date, fmtNum(x.sm, 3)]) }}
          >
            {d.soil_moisture.available && d.soil_moisture.days.length ? (
              <ResponsiveContainer>
                <LineChart data={d.soil_moisture.days} margin={{ top: 4, right: 8, bottom: 0, left: -6 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="date" tick={AXIS} tickFormatter={(x: string) => x.slice(0, 7)} minTickGap={24} />
                  <YAxis tick={AXIS} domain={["auto", "auto"]} />
                  <Tooltip content={({ active, payload }) => {
                    const x = active ? (payload?.[0]?.payload as { date: string; sm: number } | undefined) : undefined;
                    return x ? <TooltipBox title={x.date} rows={[{ label: t("monitoring.layer.moisture"), value: `${fmtNum(x.sm, 3)} ${t("units.m3m3")}`, color: C.moisture }]} /> : null;
                  }} />
                  <Line dataKey="sm" stroke={C.moisture} strokeWidth={0} dot={{ r: 2.5, fill: C.moisture, strokeWidth: 0 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Notice>{t("monitoring.no_smap")}</Notice>
            )}
          </ChartFrame>
        )}
      </div>

      <Notice>{t("monitoring.historical_note", { end: avail[1] })}</Notice>

      <section>
        <SectionTitle title={t("sources.title")} hint={t("sources.hint")} />
        <SourceList
          sources={[d.sources.power, d.sources.modis, d.sources.smap, d.sources.gpm]}
          periods={{
            power: `${avail[0]} – ${avail[1]}`,
            modis: d.ndvi.composites.length ? `${d.ndvi.composites[0]?.date} – ${d.ndvi.composites.at(-1)?.date}` : "—",
            smap: d.soil_moisture.days.length ? `${d.soil_moisture.days[0]?.date} – ${d.soil_moisture.days.at(-1)?.date}` : "—",
          }}
        />
      </section>
    </div>
  );
}
