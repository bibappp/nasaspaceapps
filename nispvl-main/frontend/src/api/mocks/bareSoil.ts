import type { BareSoil, BareSoilClimatologyMonth, BareSoilMonth, BareSoilYear } from "../types";
import exampleRaw from "../../../../docs/contracts/bare_soil.example.json";

const SEED = exampleRaw as Omit<BareSoil, "field_id" | "period" | "years" | "climatology"> & {
  _comment?: string;
  period: { start_year: number; end_year: number };
};

const DEFAULT_START = SEED.period.start_year;
const DEFAULT_END = SEED.period.end_year;

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

/** Deterministic 0..1 from year and month (stable mock grid). */
function hash01(year: number, month: number): number {
  const x = Math.sin(year * 127.1 + month * 311.7) * 43758.5453;
  return x - Math.floor(x);
}

function windDays(year: number, month: number): number {
  const dim = daysInMonth(year, month);
  return Math.min(dim, Math.round(4 + hash01(year, month + 40) * 12));
}

function monthState(year: number, month: number): BareSoilMonth["state"] {
  if (month === 12 || month === 1 || month === 2 || month === 3) return "snow";
  if (month === 11) return hash01(year, month) < 0.55 ? "snow" : hash01(year, month + 17) < 0.12 ? "missing" : "ok";
  if (hash01(year, month + 91) < 0.06) return "missing";
  return "ok";
}

function okMonthCells(year: number, month: number, dim: number): Pick<BareSoilMonth, "bare_days" | "dry_days" | "joint_days" | "exposure" | "moisture_source" | "quality"> {
  const h = hash01(year, month);
  const smapEra = year >= 2015;
  const moisture = smapEra && h > 0.25 ? "smap" : "power_gwettop";
  const quality: BareSoilMonth["quality"] = moisture === "power_gwettop" || month === 9 ? "partial" : "ok";

  if (month === 7) {
    return { bare_days: Math.round(h * 3), dry_days: Math.round(8 + h * 14), joint_days: 0, exposure: 0, moisture_source: moisture, quality: "ok" };
  }

  const seasonal =
    month === 4 || month === 5 ? 0.72 + h * 0.22
    : month === 9 || month === 10 ? 0.68 + h * 0.26
    : month === 6 || month === 8 ? 0.35 + h * 0.35
    : 0.2 + h * 0.4;

  const bare = Math.min(dim, Math.round(seasonal * dim));
  const dry = Math.min(dim, Math.round((0.35 + h * 0.35) * dim));
  const joint = Math.min(bare, Math.round(bare * (0.28 + h * 0.22)));
  const exposure = Math.round((joint / dim) * 100) / 100;

  return {
    bare_days: bare,
    dry_days: dry,
    joint_days: joint,
    exposure,
    moisture_source: moisture,
    quality,
  };
}

function buildMonth(year: number, month: number): BareSoilMonth {
  const days_in_month = daysInMonth(year, month);
  const state = monthState(year, month);
  const wind = windDays(year, month);

  if (state === "snow") {
    return {
      month,
      state,
      bare_days: null,
      erosive_wind_days: wind,
      dry_days: null,
      joint_days: null,
      days_in_month,
      exposure: null,
      moisture_source: null,
      quality: "ok",
    };
  }

  if (state === "missing") {
    return {
      month,
      state,
      bare_days: null,
      erosive_wind_days: wind,
      dry_days: null,
      joint_days: null,
      days_in_month,
      exposure: null,
      moisture_source: null,
      quality: "missing",
    };
  }

  const cells = okMonthCells(year, month, days_in_month);
  return {
    month,
    state: "ok",
    erosive_wind_days: wind,
    days_in_month,
    ...cells,
  };
}

function buildYears(start: number, end: number): BareSoilYear[] {
  const years: BareSoilYear[] = [];
  for (let year = start; year <= end; year++) {
    const months: BareSoilMonth[] = [];
    for (let month = 1; month <= 12; month++) months.push(buildMonth(year, month));
    years.push({ year, months });
  }
  return years;
}

function buildClimatology(years: BareSoilYear[]): BareSoilClimatologyMonth[] {
  const out: BareSoilClimatologyMonth[] = [];
  for (let month = 1; month <= 12; month++) {
    const exposures = years.flatMap((y) => {
      const m = y.months.find((row) => row.month === month);
      return m?.state === "ok" && m.exposure !== null ? [m.exposure] : [];
    });
    exposures.sort((a, b) => a - b);
    const n = exposures.length;
    if (!n) {
      out.push({ month, exposure_median: 0, exposure_p90: 0, n_years: 0 });
      continue;
    }
    const mid = Math.floor(n / 2);
    const median = n % 2 ? exposures[mid]! : (exposures[mid - 1]! + exposures[mid]!) / 2;
    const p90 = exposures[Math.min(n - 1, Math.ceil(n * 0.9) - 1)]!;
    out.push({ month, exposure_median: Math.round(median * 100) / 100, exposure_p90: Math.round(p90 * 100) / 100, n_years: n });
  }
  return out;
}

function topMonthsFromClimatology(clim: BareSoilClimatologyMonth[]): { top_months: number[]; max_median_exposure: number } {
  const ranked = [...clim].filter((c) => c.n_years > 0).sort((a, b) => b.exposure_median - a.exposure_median);
  const max_median_exposure = ranked[0]?.exposure_median ?? 0;
  const top_months = ranked.slice(0, 2).map((c) => c.month).sort((a, b) => a - b);
  return { top_months, max_median_exposure };
}

/** Mock GET /fields/{id}/bare-soil — full monthly grid for UI development. */
export function mockBareSoil(fieldId: number, startYear?: number, endYear?: number): BareSoil {
  const start = startYear ?? DEFAULT_START;
  const end = endYear ?? DEFAULT_END;
  const years = buildYears(start, end);
  const climatology = buildClimatology(years);
  const headline = topMonthsFromClimatology(climatology);

  return {
    field_id: fieldId,
    period: { start_year: start, end_year: end },
    status: SEED.status,
    jobs: SEED.jobs,
    headline,
    definition: SEED.definition,
    thresholds: SEED.thresholds,
    years,
    climatology,
    cover_crop_windows: SEED.cover_crop_windows,
    sources: SEED.sources,
    warnings: SEED.warnings,
  };
}