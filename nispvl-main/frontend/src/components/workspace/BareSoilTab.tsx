import { useEffect, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../api/client";
import type { BareSoil, BareSoilJob, BareSoilMonth, DataWarning, Job, Lang } from "../../api/types";
import { errorText, useAsync } from "../../lib/async";
import { RAMPS } from "../../lib/colors";
import { fmtNum } from "../../lib/format";
import { tx } from "../../lib/i18n-text";
import ChartFrame, { AXIS, C, GRID, TooltipBox } from "../charts/ChartFrame";
import StatusBadge from "../common/StatusBadge";
import { EmptyState, ErrorBox, KindBadge, Loading, Notice, SectionTitle } from "../ui/ui";
import SourceList from "./SourceList";

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as const;
const COLS = "3.25rem repeat(12, minmax(2.75rem, 1fr))";
const SNOW_BG = "repeating-linear-gradient(135deg, #e4e7eb 0 3px, #c5cad1 3px 5px)";
const exposureRamp = RAMPS.exposure ?? RAMPS.ndvi!;

interface CellPos {
  y: number;
  m: number;
}

interface ClimRow {
  month: number;
  label: string;
  median: number | null;
  p90: number | null;
  n: number;
}

function contrastInk(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.62 ? "#1F2328" : "#ffffff";
}

function monthList(months: number[], t: TFunction): string {
  const names = [...months].sort((a, b) => a - b).map((m) => t(`bare_soil.month.${m}`));
  if (names.length === 0) return "";
  if (names.length === 1) return names[0] ?? "";
  const last = names[names.length - 1] ?? "";
  return t("bare_soil.months_pair", { a: names.slice(0, -1).join(", "), b: last });
}

function fmtMonthDay(md: string, t: TFunction): string {
  const [ms, ds] = md.split("-");
  const month = Number(ms);
  const day = Number(ds);
  if (!month || !day || month < 1 || month > 12) return md;
  return t("bare_soil.month_day", { day, month: t(`bare_soil.month_short.${month}`) });
}

function moistureLabel(src: string | null, t: TFunction): string {
  if (src === "smap") return t("bare_soil.moisture_smap");
  if (src === "power_gwettop") return t("bare_soil.moisture_power");
  if (!src) return t("bare_soil.moisture_none");
  return src;
}

function warningText(w: DataWarning, t: TFunction): string {
  const vars: Record<string, string | number> = { source: w.source };
  for (const [k, v] of Object.entries(w.params)) {
    if (typeof v === "number" || typeof v === "string") vars[k] = v;
    else if (typeof v === "boolean") vars[k] = v ? "true" : "false";
    else if (Array.isArray(v)) vars[k] = v.map(String).join(", ");
  }
  return t(`warnings.${w.code}`, { ...vars, defaultValue: w.code });
}

function thresholdLabel(id: string, t: TFunction): string {
  const key = `bare_soil.threshold.${id}`;
  const label = t(key);
  return label === key ? id : label;
}

function useBareSoilPolling(data: BareSoil | null, reload: () => void) {
  const pending =
    data && (data.status === "partial" || data.status === "loading")
      ? data.jobs.filter((j) => j.status === "pending" && j.job)
      : [];
  const key = pending.map((j) => j.job?.id).filter((id): id is string => Boolean(id)).join("|");
  const [live, setLive] = useState<Record<string, Job>>({});

  useEffect(() => {
    if (!key) return;
    let alive = true;
    const ids = key.split("|");
    const timer = window.setInterval(() => {
      void Promise.all(ids.map((id) => api.job(id).catch(() => null))).then((js) => {
        if (!alive) return;
        setLive((prev) => {
          const next = { ...prev };
          for (const job of js) if (job) next[job.id] = job;
          return next;
        });
        if (js.some((j) => !j || j.status !== "running")) reload();
      });
    }, 4000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [key, reload]);

  return { pending, live };
}

function jobSnapshot(j: BareSoilJob, live: Record<string, Job>): Job | undefined {
  if (!j.job) return undefined;
  return live[j.job.id] ?? j.job;
}

export default function BareSoilTab({ fieldId }: { fieldId: number }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const res = useAsync(() => api.fieldBareSoil(fieldId), [fieldId]);
  const { pending, live } = useBareSoilPolling(res.data, res.reload);
  const [pinned, setPinned] = useState<CellPos | null>(null);
  const [hover, setHover] = useState<CellPos | null>(null);

  if (res.error) return <ErrorBox message={errorText(res.error, t)} onRetry={res.reload} />;
  if (!res.data) return <Loading />;
  const d = res.data;

  const years = [...d.years].sort((a, b) => b.year - a.year);
  const hasYear = years.some((y) => y.months.length > 0);
  const shown = hover ?? pinned;
  const shownYear = shown ? years.find((y) => y.year === shown.y) : undefined;
  const shownCell: BareSoilMonth | null = shownYear?.months.find((m) => m.month === shown?.m) ?? null;
  const period = `${d.period.start_year}–${d.period.end_year}`;
  const sourceLine = d.sources.map((s) => `${s.title} (${tx(s.spatial_resolution, lang) || "—"})`).join(" · ");
  const headline = d.headline.top_months.length
    ? t("bare_soil.headline", { months: monthList(d.headline.top_months, t) })
    : t("bare_soil.headline_none");

  const climByMonth = new Map(d.climatology.map((c) => [c.month, c]));
  const climRows: ClimRow[] = MONTHS.map((month) => {
    const c = climByMonth.get(month);
    const known = Boolean(c && c.n_years > 0);
    return {
      month,
      label: t(`bare_soil.month_short.${month}`),
      median: known && c ? c.exposure_median : null,
      p90: known && c ? c.exposure_p90 : null,
      n: c?.n_years ?? 0,
    };
  });
  const climHas = climRows.some((r) => r.n > 0);
  const yMax = Math.max(1, ...climRows.map((r) => Math.max(r.median ?? 0, r.p90 ?? 0)));
  const firstYear = years[0];
  const tabPos = pinned ?? (firstYear ? { y: firstYear.year, m: 1 } : null);

  const moveFocus = (year: number, month: number, dy: number, dm: number) => {
    const yi = years.findIndex((row) => row.year === year);
    const next = years[yi + dy];
    const nextM = month + dm;
    if (yi < 0 || !next || nextM < 1 || nextM > 12) return;
    const pos = { y: next.year, m: nextM };
    setPinned(pos);
    requestAnimationFrame(() => document.getElementById(`bare-soil-cell-${pos.y}-${pos.m}`)?.focus());
  };

  return (
    <div className="min-w-0 space-y-6" aria-busy={pending.length > 0}>
      {pending.length > 0 && (
        <Notice>
          <p>{t("bare_soil.pending", { sources: pending.map((j) => j.source).join(", ") })}</p>
          <ul className="mt-2 space-y-2">
            {pending.map((j) => {
              const job = jobSnapshot(j, live);
              const pct = job && job.total > 0 ? Math.round((job.done / job.total) * 100) : null;
              return (
                <li key={j.job?.id ?? j.source}>
                  <div className="flex justify-between gap-3 text-xs">
                    <span>{t("bare_soil.pending_progress", { source: j.source, done: job?.done ?? 0, total: job?.total ?? 0 })}</span>
                    {pct !== null && <span className="tabular-nums">{pct}%</span>}
                  </div>
                  {pct !== null && (
                    <div
                      className="mt-1 h-1.5 overflow-hidden rounded bg-white"
                      role="progressbar"
                      aria-valuenow={job?.done ?? 0}
                      aria-valuemin={0}
                      aria-valuemax={job?.total ?? 0}
                      aria-label={j.source}
                    >
                      <div className="h-full bg-field-700" style={{ width: `${pct}%` }} />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </Notice>
      )}

      <header>
        <h2 className="h2">{headline}</h2>
        {d.headline.top_months.length > 0 && (
          <p className="mt-1 text-sm text-ink-muted">{t("bare_soil.headline_peak", { value: fmtNum(d.headline.max_median_exposure, 2) })}</p>
        )}
        <p className="mt-2 text-sm leading-relaxed text-ink-2">{tx(d.definition.exposure, lang)}</p>
      </header>

      {!hasYear ? (
        <EmptyState
          title={t("bare_soil.empty_title")}
          text={pending.length > 0 ? t("bare_soil.empty_pending") : t("bare_soil.empty_text")}
        />
      ) : (
        <section className="panel min-w-0">
          <div className="panel-head">
            <h3 className="h3">{t("bare_soil.grid_title")}</h3>
          </div>
          <div className="overflow-x-auto overscroll-x-contain">
            <div className="min-w-[36.5rem] px-4 py-3" role="grid" aria-label={t("bare_soil.grid_label")}>
              <div role="row" className="grid gap-1" style={{ gridTemplateColumns: COLS }}>
                <div role="columnheader" className="sticky left-0 z-10 bg-white" />
                {MONTHS.map((m) => (
                  <div key={m} role="columnheader" className="pb-1 text-center text-[10px] font-medium uppercase tracking-wide text-ink-muted">
                    {t(`bare_soil.month_short.${m}`)}
                  </div>
                ))}
              </div>
              {years.map((year) => (
                <div key={year.year} role="row" className="mt-1 grid gap-1" style={{ gridTemplateColumns: COLS }}>
                  <div role="rowheader" className="sticky left-0 z-10 flex items-center bg-white pr-1 text-xs font-semibold tabular-nums text-ink">
                    {year.year}
                  </div>
                  {MONTHS.map((month) => {
                    const cell = year.months.find((row) => row.month === month) ?? null;
                    const partial = cell?.quality === "partial";
                    const snow = cell?.state === "snow";
                    const value = cell?.state === "ok" ? cell.exposure : null;
                    const colored = value !== null;
                    const bg = colored ? exposureRamp(Math.min(1, Math.max(0, value))) : undefined;
                    const selected = shown?.y === year.year && shown.m === month;
                    const labelValue = snow
                      ? t("bare_soil.snow")
                      : value === null
                        ? t("bare_soil.missing")
                        : fmtNum(value, 2);
                    return (
                      <button
                        key={month}
                        id={`bare-soil-cell-${year.year}-${month}`}
                        type="button"
                        role="gridcell"
                        aria-pressed={selected}
                        aria-controls="bare-soil-detail"
                        tabIndex={tabPos?.y === year.year && tabPos.m === month ? 0 : -1}
                        aria-label={t("bare_soil.cell_label", {
                          month: t(`bare_soil.month.${month}`),
                          year: year.year,
                          value: labelValue,
                          quality: t(`bare_soil.quality_${cell?.quality ?? "missing"}`),
                        })}
                        onMouseEnter={() => setHover({ y: year.year, m: month })}
                        onMouseLeave={() => setHover(null)}
                        onFocus={() => {
                          setHover(null);
                          setPinned({ y: year.year, m: month });
                        }}
                        onClick={() => setPinned({ y: year.year, m: month })}
                        onKeyDown={(e) => {
                          const step: Record<string, [number, number]> = {
                            ArrowRight: [0, 1],
                            ArrowLeft: [0, -1],
                            ArrowDown: [1, 0],
                            ArrowUp: [-1, 0],
                          };
                          const delta = step[e.key];
                          const dy = delta?.[0];
                          const dm = delta?.[1];
                          if (dy === undefined || dm === undefined) return;
                          e.preventDefault();
                          moveFocus(year.year, month, dy, dm);
                        }}
                        className={`relative flex h-11 w-full items-center justify-center rounded-sm text-[11px] font-semibold leading-none ${
                          selected ? "ring-2 ring-inset ring-field-800" : ""
                        } ${snow ? "text-ink" : colored ? "" : "border border-dashed border-line-strong bg-white text-ink-subtle"}`}
                        style={
                          snow
                            ? { backgroundImage: SNOW_BG }
                            : colored && bg
                              ? { background: bg, color: contrastInk(bg) }
                              : undefined
                        }
                      >
                        {partial && (
                          <span className="pointer-events-none absolute right-0 top-0 h-0 w-0 border-l-[8px] border-t-[8px] border-l-transparent border-t-status-info" aria-hidden />
                        )}
                        {snow ? t("bare_soil.snow") : value === null ? "—" : fmtNum(value, 2)}
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
          <div className="panel-body space-y-4 border-t border-line">
            <ul className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-2">
              <li className="min-w-[10rem] flex-1">
                <div
                  className="h-2 rounded-sm"
                  style={{ background: `linear-gradient(90deg, ${[0, 0.25, 0.5, 0.75, 1].map((stop) => `${exposureRamp(stop)} ${stop * 100}%`).join(", ")})` }}
                />
                <div className="mt-1 flex justify-between tabular-nums text-ink-muted">
                  <span>{fmtNum(0, 0)}</span>
                  <span>{fmtNum(1, 0)}</span>
                </div>
                <div className="text-ink-muted">{t("bare_soil.legend_unit")}</div>
              </li>
              <li className="flex items-center gap-1.5">
                <span className="inline-block h-4 w-6 rounded-sm border border-line" style={{ backgroundImage: SNOW_BG }} aria-hidden />
                {t("bare_soil.snow")}
              </li>
              <li className="flex items-center gap-1.5">
                <span className="inline-flex h-4 w-6 items-center justify-center rounded-sm border border-dashed border-line-strong text-[10px]" aria-hidden>—</span>
                {t("bare_soil.missing")}
              </li>
              <li className="flex items-center gap-1.5">
                <span className="relative inline-block h-4 w-6 rounded-sm border border-line bg-soil-100" aria-hidden>
                  <span className="absolute right-0 top-0 h-0 w-0 border-l-[8px] border-t-[8px] border-l-transparent border-t-status-info" />
                </span>
                {t("bare_soil.partial_marker")}
              </li>
            </ul>

            <div id="bare-soil-detail" aria-live="polite" className="rounded-md border border-line bg-surface-sunken p-3">
              {shown ? (
                <>
                  <h4 className="h3">{t("bare_soil.detail_title", { month: t(`bare_soil.month.${shown.m}`), year: shown.y })}</h4>
                  <dl className="mt-3 grid gap-3 sm:grid-cols-2">
                    <Detail label={t("bare_soil.exposure")} value={fmtNum(shownCell?.state === "ok" ? shownCell.exposure : null, 2)} />
                    <Detail label={t("bare_soil.state")} value={t(`bare_soil.state_${shownCell?.state ?? "missing"}`)} />
                    <Detail label={t("bare_soil.bare_days")} value={fmtNum(shownCell?.bare_days, 0)} />
                    <Detail label={t("bare_soil.wind_days")} value={shownCell ? fmtNum(shownCell.erosive_wind_days, 0) : "—"} />
                    <Detail label={t("bare_soil.dry_days")} value={fmtNum(shownCell?.dry_days, 0)} />
                    <Detail
                      label={t("bare_soil.joint")}
                      value={
                        shownCell
                          ? t("bare_soil.joint_value", { joint: fmtNum(shownCell.joint_days, 0), days: shownCell.days_in_month })
                          : "—"
                      }
                    />
                    <Detail label={t("bare_soil.moisture")} value={moistureLabel(shownCell?.moisture_source ?? null, t)} />
                    <div>
                      <dt className="text-xs text-ink-muted">{t("bare_soil.quality")}</dt>
                      <dd className="mt-0.5">
                        <span className={shownCell?.quality === "ok" ? "badge-green" : shownCell?.quality === "partial" ? "badge-amber" : "badge-neutral"}>
                          {t(`bare_soil.quality_${shownCell?.quality ?? "missing"}`)}
                        </span>
                      </dd>
                    </div>
                  </dl>
                </>
              ) : (
                <p className="text-sm text-ink-muted">{t("bare_soil.select_hint")}</p>
              )}
            </div>

            <p className="text-xs leading-relaxed text-ink-muted">
              <KindBadge kind="observation" /> <KindBadge kind="reanalysis" /> {sourceLine || "—"}. {t("bare_soil.heatmap_caption", { start: d.period.start_year, end: d.period.end_year })}
            </p>
          </div>
        </section>
      )}

      <ChartFrame
        title={t("bare_soil.clim_title")}
        legend={[
          { color: C.dry, label: t("bare_soil.clim_median") },
          { color: C.moisture, label: t("bare_soil.clim_p90") },
        ]}
        caption={
          <>
            <KindBadge kind="statistic" /> {sourceLine || "—"}. {t("bare_soil.clim_caption", { start: d.period.start_year, end: d.period.end_year })}
          </>
        }
        table={{
          columns: [t("bare_soil.clim_month"), t("bare_soil.clim_median"), t("bare_soil.clim_p90"), t("bare_soil.clim_years")],
          rows: climRows.map((r) => [r.label, fmtNum(r.median, 2), fmtNum(r.p90, 2), r.n]),
        }}
        height={280}
      >
        {climHas ? (
          <ResponsiveContainer>
            <ComposedChart data={climRows} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="label" tick={AXIS} interval={0} angle={-40} textAnchor="end" height={48} />
              <YAxis tick={AXIS} domain={[0, yMax]} width={36} />
              <Tooltip
                content={({ active, payload }) => {
                  const row = active ? (payload?.[0]?.payload as ClimRow | undefined) : undefined;
                  return row ? (
                    <TooltipBox
                      title={t(`bare_soil.month.${row.month}`)}
                      rows={[
                        { label: t("bare_soil.clim_median"), value: fmtNum(row.median, 2), color: C.dry },
                        { label: t("bare_soil.clim_p90"), value: fmtNum(row.p90, 2), color: C.moisture },
                        { label: t("bare_soil.clim_years"), value: String(row.n) },
                      ]}
                    />
                  ) : null;
                }}
              />
              <Bar dataKey="median" fill={C.dry} radius={[3, 3, 0, 0]} maxBarSize={28} isAnimationActive={false} />
              <Line dataKey="p90" stroke="transparent" strokeWidth={0} dot={{ r: 4, fill: C.moisture, stroke: "#fff", strokeWidth: 1 }} activeDot={{ r: 5 }} isAnimationActive={false} connectNulls={false} legendType="circle" />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <Notice>{t("bare_soil.clim_empty")}</Notice>
        )}
      </ChartFrame>

      <section>
        <SectionTitle title={t("bare_soil.windows_title")} hint={t("bare_soil.windows_hint")} />
        {d.cover_crop_windows.length === 0 ? (
          <Notice>{t("bare_soil.windows_empty")}</Notice>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {d.cover_crop_windows.map((w) => (
              <article key={`${w.start}-${w.end}`} className="card">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h3 className="h3">{t("bare_soil.window_range", { start: fmtMonthDay(w.start, t), end: fmtMonthDay(w.end, t) })}</h3>
                  <span className={w.uncertainty === "low" ? "badge-green" : w.uncertainty === "high" ? "badge-red" : "badge-amber"}>
                    {t("bare_soil.uncertainty")}: {t(`bare_soil.uncertainty_${w.uncertainty}`)}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">{tx(w.basis, lang)}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      {d.thresholds.length > 0 && (
        <section>
          <SectionTitle title={t("bare_soil.thresholds_title")} hint={t("bare_soil.thresholds_hint")} />
          <div className="panel overflow-x-auto">
            <table className="table min-w-[640px]">
              <thead>
                <tr>
                  <th>{t("bare_soil.col_id")}</th>
                  <th className="num">{t("bare_soil.col_value")}</th>
                  <th>{t("bare_soil.col_unit")}</th>
                  <th>{t("bare_soil.col_source")}</th>
                  <th>{t("bare_soil.col_status")}</th>
                </tr>
              </thead>
              <tbody>
                {d.thresholds.map((th) => (
                  <tr key={th.id}>
                    <td>{thresholdLabel(th.id, t)}</td>
                    <td className="num">{fmtNum(th.value, Math.abs(th.value) < 1 ? 2 : 1)}</td>
                    <td className="text-xs text-ink-2">{th.unit}</td>
                    <td className="text-xs">{th.source}</td>
                    <td><StatusBadge status={th.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {d.warnings.map((w, i) => (
        <Notice key={`${w.code}-${w.source}-${i}`} tone="warn">{warningText(w, t)}</Notice>
      ))}

      <section>
        <SectionTitle title={t("sources.title")} hint={t("sources.hint")} />
        <SourceList sources={d.sources} periods={Object.fromEntries(d.sources.map((s) => [s.id, period]))} />
      </section>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular-nums text-ink">{value}</dd>
    </div>
  );
}
