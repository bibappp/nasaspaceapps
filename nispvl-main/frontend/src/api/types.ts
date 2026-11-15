// Типы ответов API бэкенда (backend/app/api/routes.py).
import type { Polygon } from "geojson";

export type Lang = "ru" | "kk" | "en";
export type I18nText = Record<Lang, string>;
export type Status = "verified" | "assumption";
export type Evidence = "literature" | "agronomist_review" | "preliminary" | "definition";
export type Origin = "live" | "cache" | "demo" | "fallback" | "unavailable" | null;

export interface CropInfo {
  id: string;
  name: I18nText;
  short: I18nText;
  group: "cereal" | "legume" | "oilseed" | "fallow";
  nitrogen_fixing: boolean;
}

export interface Variant {
  id: string;
  name?: I18nText | null;
  crops: string[];
  custom?: boolean;
}

export interface AppConfig {
  crops: CropInfo[];
  regions: { id: string; name: I18nText }[];
  priorities: { id: string; name: I18nText; weights: Record<ScoreKey, number> }[];
  default_variants: Variant[];
  horizon: { default_years: number; min_years: number; max_years: number };
  history: { min_years: number; max_years: number };
  season_months: number[];
  presowing_months: number[];
}

export interface HistoryItem {
  year: number;
  crop: string;
}

export interface FieldRequest {
  geometry: Polygon;
  region: string;
  history: HistoryItem[];
  priority: string;
  horizon_years: number;
}

export interface CompareRequest extends FieldRequest {
  variants?: Variant[];
  start_year?: number;
}

export interface ReportRequest extends CompareRequest {
  lang: Lang;
  selected_variant_id?: string;
  farm_name?: string;
  stress_year_index?: number;
}

export interface DataWarning {
  code: string;
  source: string;
  params: Record<string, unknown>;
}

export interface Job {
  id: string;
  kind: string;
  status: "running" | "done" | "failed";
  done: number;
  total: number;
  error: string | null;
}

export interface SlowState {
  status: "ready" | "pending" | "not_configured" | "not_started" | "unavailable";
  origin?: Origin;
  reason?: string | null;
  job?: Job;
}

export interface Resolution {
  source: string;
  title: string;
  resolution_m: number | null;
  spatial_resolution: I18nText;
  provenance: I18nText;
  temporal_coverage: I18nText;
}

export interface DroughtYear {
  year: number;
  precip_mm: number;
  anomaly: number;
  is_dry: boolean;
  by_percentile: boolean;
  by_anomaly: boolean;
}

export interface NdviTrend {
  yearly_max: { year: number; ndvi: number; date: string; n_composites: number }[];
  label: "rising" | "declining" | "stable" | "insufficient";
  slope_per_year: number | null;
  slope_pct_per_decade?: number | null;
  p_value: number | null;
  r2?: number;
  from_year?: number;
  to_year?: number;
  n_years?: number;
  p_threshold?: number;
  intercept?: number;
}

export interface SoilLayer {
  depth: string;
  sand_pct: number;
  clay_pct: number;
  soc_g_kg: number;
  humus_pct: number;
  ph: number | null;
  awc_mm: number;
}

export interface Analysis {
  field: {
    area_ha: number;
    centroid: { lat: number; lon: number };
    bbox: [number, number, number, number];
    region: string;
    region_name: I18nText;
    is_demo: boolean;
    geometry: Polygon;
  };
  climate: {
    origin: Origin;
    series_from: number;
    series_to: string;
    season_precip: { year: number; precip_mm: number; t_mean?: number; hot_days?: number }[];
    normal_precip_mm: number;
    elevation_m: number | null;
  };
  drought: {
    definition: {
      baseline: [number, number];
      percentile: number;
      percentile_mm: number;
      anomaly_threshold: number;
      baseline_mean_mm: number;
      baseline_std_mm: number;
    };
    years: DroughtYear[];
    window: { from: number; to: number; n_years: number } | null;
    dry_years: number[];
    share: number;
    every_nth: number | null;
    driest_year: number | null;
    median_mm: number | null;
    stress_year: number;
    stress_year_reason: "default_year" | "driest_year";
  };
  ndvi: {
    state: SlowState;
    series?: { date: string; ndvi: number | null; valid_fraction: number }[];
    trend?: NdviTrend;
    n_field_pixels?: number;
    missing_years?: number[];
    raster_dates?: string[];
    origin?: Origin;
  };
  soil_moisture: {
    state: SlowState;
    basis: "smap" | "power";
    smap_by_year: { year: number; mean: number; n_days: number }[];
    power_gwetroot_by_year: { year: number; value: number }[];
    stock: {
      norm_mm: number;
      awc_mm: number | null;
      normal_stock_mm: number;
      by_year: { year: number; ratio: number; basis: string; stock_mm: number; capped: boolean }[];
      uses_smap: boolean;
    };
    cell: { row: number; col: number; lon: number; lat: number } | null;
    origin: Origin;
  };
  soil: {
    origin: Origin;
    summary: {
      layers: SoilLayer[];
      awc_mm: number;
      root_zone_cm: number;
      topsoil: { humus_pct: number | null; clay_pct: number | null; sand_pct: number | null; ph: number | null };
      texture_class: string;
    } | null;
  };
  conditions: Conditions;
  region_reference: { season_precip_mm: number; presowing_stock_mm: number; rules: ParamRef[] };
  resolutions: Resolution[];
  warnings: DataWarning[];
  sources: { source: string; origin: Origin; status?: string; job?: Job }[];
}

export interface Conditions {
  region: string;
  area_ha: number;
  p_season_normal: number;
  stock_normal: number;
  p_season_dry: number;
  stock_dry: number;
  dry_year: number;
  p_season_ref: number;
  stock_ref: number;
  awc_mm: number | null;
  moisture_basis: "smap" | "power";
}

export interface ParamRef {
  path: string;
  value: unknown;
  unit: string;
  status: Status;
  evidence: Evidence;
  source: string;
  url: string;
}

export type ScoreKey = "soil" | "water" | "income" | "risk";

export interface Score {
  score: number;
  metric: string;
  value: number;
  unit: string;
  better: "higher" | "lower";
  scale_min: number;
  scale_max: number;
  pool_size: number;
  params: ParamRef[];
  assumptions: number;
}

export interface YearResult {
  index: number;
  year: number;
  crop: string;
  group: string;
  predecessor: string | null;
  base_yield_t_ha: number;
  predecessor_effect_pct: number;
  monoculture: boolean;
  monoculture_penalty_pct: number;
  after_fallow: boolean;
  stock_mm: number;
  water_available_mm: number;
  water_need_mm: number;
  water_deficit_mm: number;
  moisture_coef: number;
  moisture_coef_dry: number;
  yield_t_ha: number;
  yield_dry_t_ha: number;
  yield_loss_dry_pct: number;
  price_kzt_t: number;
  cost_kzt_ha: number;
  income_kzt_ha: number;
  income_dry_kzt_ha: number;
  soil_index: number;
  revenue_kzt_ha: number;
  nitrogen_kg_ha: number;
  humus_t_ha: number;
  soil_delta: number;
  predecessor_rule: string | null;
}

export interface VariantResult {
  id: string;
  name?: I18nText | null;
  custom: boolean;
  crops: string[];
  years: YearResult[];
  totals: {
    income_kzt_ha: number;
    income_per_year_kzt_ha: number;
    income_field_kzt: number;
    nitrogen_kg_ha: number;
    humus_t_ha: number;
    soil_index_end: number;
    soil_index_change: number;
    water_deficit_mean_mm: number;
    monoculture_years: number;
    drought_loss_pct: number;
    revenue_kzt_ha: number;
    drought_loss_mean_kzt_ha: number;
  };
  stress: {
    per_year: {
      index: number;
      year: number;
      crop: string;
      income_normal_kzt_ha: number;
      income_dry_kzt_ha: number;
      loss_kzt_ha: number;
      total_if_dry_kzt_ha: number;
    }[];
    total_normal_kzt_ha: number;
    worst_year_index: number;
    worst_loss_kzt_ha: number;
  };
  scores: Record<ScoreKey, Score>;
  weighted_score: number;
  fits_priority: boolean;
  params_used: number;
  assumptions_used: number;
  explanation: ({ code: string } & I18nText)[];
  confidence: Confidence;
  economics: Economics;
}

export interface Comparison {
  start_year: number;
  horizon_years: number;
  priority: string;
  priority_name: I18nText;
  weights: Record<ScoreKey, number> & { _rule: ParamRef };
  conditions: Conditions;
  reference_water_mm: number;
  normal_water_mm: number;
  dry_water_mm: number;
  variants: VariantResult[];
  best_variant_id: string;
  baseline_variant_id: string;
  warnings: DataWarning[];
  weights_custom?: boolean;
  drought?: { stress_year: number; stress_year_reason: string; dry_years: number[]; share: number; every_nth: number | null };
  history?: HistoryItem[];
}

export interface DemoField {
  id: string;
  name: I18nText;
  region: string;
  geometry: Polygon;
  history: HistoryItem[];
  history_is_scenario: boolean;
  history_note: I18nText;
  priority: string;
  horizon_years: number;
  area_ha: number;
}

export interface LayerResponse {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: Polygon;
    properties: { value: number | null; in_field: boolean };
  }[];
  meta: {
    source: string;
    source_title: string;
    resolution_m: number | null;
    spatial_resolution: I18nText;
    kind: string;
    date: string;
    dates: string[];
    unit: string;
    legend: { min: number; max: number };
    fallback_for?: string;
  };
}

export interface RuleParam {
  path: string;
  value: unknown;
  unit: string;
  source: { id: string; name: string; url: string };
  status: Status;
  evidence: Evidence;
  note: string;
}

export interface DataSourceInfo {
  id: string;
  title: string;
  provider: string;
  url: string;
  doi?: string;
  used_for: I18nText;
  provenance: I18nText;
  spatial_resolution: I18nText;
  temporal_coverage: I18nText;
  access: I18nText;
  limitations: I18nText;
  checked: string;
  status: string;
  state: "active" | "planned" | "needs_credentials" | "offline";
}

export interface RulesCatalog {
  params: RuleParam[];
  counts: { total: number; verified: number; assumption: number; by_evidence: Record<Evidence, number> };
  rule_sources: { id: string; name: string; url: string }[];
  todo_sources: { id: string; name: string; url: string }[];
  data_sources: DataSourceInfo[];
}

export interface LandingFact {
  name: string;
  url: string;
}

// ---------------------------------------------------------------- учётные записи и поля
export interface User {
  id: number;
  email: string;
  name: string;
  farm_name: string;
  lang: Lang;
  is_demo: boolean;
  created_at: string;
}

export interface SoilInfo {
  humus_pct: number | null;
  ph: number | null;
  texture: "sand" | "sandy_loam" | "loam" | "clay_loam" | "clay" | null;
  soil_type: string;
  survey_year: number | null;
  notes: string;
}

export interface FieldRecord {
  id: number;
  name: string;
  region: string;
  geometry: Polygon;
  area_ha: number;
  centroid_lat: number;
  centroid_lon: number;
  soil: SoilInfo;
  notes: string;
  history: HistoryItem[];
  history_is_scenario: boolean;
  created_at: string;
  updated_at: string;
  n_analyses?: number;
  last_analysis_at?: string | null;
}

export interface FieldInput {
  name: string;
  region: string;
  geometry: Polygon;
  history: HistoryItem[];
  history_is_scenario: boolean;
  soil: SoilInfo;
  notes: string;
}

export type ScoreWeights = Record<ScoreKey, number>;

export interface AnalysisInput {
  title?: string;
  priority: string;
  weights?: ScoreWeights | null;
  horizon_years: number;
  variants?: Variant[];
  start_year?: number;
  stress_year?: number | null;
}

export interface AnalysisSummary {
  best_variant_id: string;
  best_variant_name: I18nText | null;
  best_crops: string[];
  priority: string;
  weights: ScoreWeights;
  weights_custom: boolean;
  horizon_years: number;
  start_year: number;
  stress_year: number;
  variants: { id: string; name: I18nText | null; crops: string[]; weighted_score: number; gross_margin_kzt_ha: number; confidence: string }[];
}

export interface AnalysisListItem {
  id: number;
  field_id: number;
  field_name: string;
  title: string;
  summary: AnalysisSummary;
  created_at: string;
}

export interface SavedAnalysis extends AnalysisListItem {
  request: AnalysisInput;
  result: Comparison;
}

// ---------------------------------------------------------------- мониторинг
export type DataKind = "observation" | "reanalysis" | "statistic" | "model";

export interface MonthlyClimate {
  month: string;
  precip_mm: number | null;
  precip_normal_mm: number | null;
  precip_pct_of_normal: number | null;
  t_mean: number | null;
  t_normal: number | null;
  t_anomaly: number | null;
  t_max_mean: number | null;
  hot_days: number;
  gwetroot: number | null;
}

export interface SourceMeta {
  id: string;
  title: string;
  resolution_m: number | null;
  origin: Origin;
  spatial_resolution: I18nText;
  provenance: I18nText;
  state?: string;
}

export interface Monitoring {
  range: { start: string; end: string };
  climate: { months: MonthlyClimate[]; baseline: [number, number]; available: [string, string] };
  ndvi: {
    available: boolean;
    composites: { date: string; ndvi: number | null; valid_fraction: number; median: number | null; p10: number | null; p90: number | null; anomaly: number | null }[];
    n_field_pixels?: number;
  };
  soil_moisture: { available: boolean; days: { date: string; sm: number }[] };
  sources: Record<"power" | "modis" | "smap" | "gpm", SourceMeta>;
  jobs: { source: string; status?: string; job?: Job }[];
  hot_day_threshold_c: number;
}

export interface SeasonRow {
  year: number;
  precip_mm: number;
  precip_anomaly_z: number;
  is_dry: boolean;
  t_mean: number | null;
  t_anomaly: number | null;
  t_anomaly_z: number | null;
  hot_days: number | null;
  ndvi_max: number | null;
  ndvi_max_date: string | null;
  ndvi_mean: number | null;
  n_composites: number;
  smap_spring: number | null;
  smap_ratio: number | null;
  gwet_spring: number | null;
}

export interface Seasons {
  years: SeasonRow[];
  window_averages: Record<string, number | null>;
  baseline: { years: [number, number]; t_mean: number; t_sd: number; hot_days: number; precip_mean: number; precip_sd: number };
  ndvi_curves: Record<string, { doy: number; date: string; ndvi: number }[]>;
  ndvi_climatology: { doy: number; median: number; p10: number; p90: number }[];
  ndvi_trend: NdviTrend | null;
  hot_day_threshold_c: number;
}

export type RiskLevel = "low" | "moderate" | "high" | "unknown";

export interface RiskItem {
  id: string;
  kind: DataKind;
  source: string;
  period?: string | null;
  value?: number | null;
  unit?: string;
  reference?: number | null;
  z?: number | null;
  percentile?: number | null;
  ratio?: number | null;
  every_nth?: number | null;
  dry_years?: number[];
  threshold_c?: number;
  fallback_for?: string;
  crop?: string;
  level: RiskLevel;
}

export interface Risk {
  latest_season: number;
  overall: RiskLevel;
  items: RiskItem[];
  thresholds: Record<string, ParamRef>;
  warnings: DataWarning[];
}

export interface SuitabilityCrop {
  crop: string;
  group: string;
  category: "favourable" | "conditional" | "limited";
  flags: ("moisture" | "predecessor" | "monoculture" | "drought" | "margin")[];
  water_need_mm: number;
  water_available_mm: number;
  moisture_coef: number;
  ky: number;
  drought_loss_pct: number;
  predecessor: string | null;
  predecessor_effect_pct: number;
  monoculture: boolean;
  yield_t_ha: number;
  gross_margin_kzt_ha: number;
  confidence: Confidence;
}

export interface Suitability {
  crops: SuitabilityCrop[];
  context: {
    water_normal_mm: number;
    water_dry_mm: number;
    dry_year: number;
    gdd5_may_sep_mean: number | null;
    gdd_years: [number, number] | null;
    soil: { humus_pct: number | null; clay_pct: number | null; sand_pct: number | null; ph: number | null } | null;
    predecessor: string | null;
  };
  thresholds: Record<string, ParamRef>;
}

export interface Confidence {
  params_total: number;
  params_supported: number;
  share: number;
  level: "high" | "medium" | "low";
  by_evidence: Record<string, number>;
}

export interface Economics {
  revenue_kzt_ha: number;
  cost_kzt_ha: number;
  gross_margin_kzt_ha: number;
  margin_price_minus20_kzt_ha: number;
  margin_price_plus20_kzt_ha: number;
  breakeven_price_factor: number | null;
  per_year: { year: number; crop: string; revenue_kzt_ha: number; cost_kzt_ha: number; gross_margin_kzt_ha: number }[];
}

export type BareSoilMonthState = "ok" | "snow" | "missing";
export type BareSoilMonthQuality = "ok" | "partial" | "missing";

export interface BareSoilMonth {
  month: number;
  state: BareSoilMonthState;
  bare_days: number | null;
  erosive_wind_days: number;
  dry_days: number | null;
  joint_days: number | null;
  days_in_month: number;
  exposure: number | null;
  moisture_source: string | null;
  quality: BareSoilMonthQuality;
}

export interface BareSoilYear {
  year: number;
  months: BareSoilMonth[];
}

export interface BareSoilThreshold {
  id: string;
  value: number;
  unit: string;
  source: string;
  status: Status;
  evidence: Evidence;
  note: string;
}

export interface BareSoilClimatologyMonth {
  month: number;
  exposure_median: number;
  exposure_p90: number;
  n_years: number;
}

export interface BareSoilCoverCropWindow {
  start: string;
  end: string;
  basis: I18nText;
  uncertainty: "low" | "medium" | "high";
}

export interface BareSoilJob {
  source: string;
  status: string;
  job?: Job;
}

export interface BareSoil {
  field_id: number;
  period: { start_year: number; end_year: number };
  status: string;
  jobs: BareSoilJob[];
  headline: { top_months: number[]; max_median_exposure: number };
  definition: { exposure: I18nText };
  thresholds: BareSoilThreshold[];
  years: BareSoilYear[];
  climatology: BareSoilClimatologyMonth[];
  cover_crop_windows: BareSoilCoverCropWindow[];
  sources: SourceMeta[];
  warnings: DataWarning[];
}
