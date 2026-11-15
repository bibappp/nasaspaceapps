import type {
  Analysis,
  AnalysisInput,
  AnalysisListItem,
  AppConfig,
  BareSoil,
  CompareRequest,
  Comparison,
  DemoField,
  FieldInput,
  FieldRecord,
  FieldRequest,
  Job,
  Lang,
  LandingFact,
  LayerResponse,
  Monitoring,
  ReportRequest,
  Risk,
  RulesCatalog,
  SavedAnalysis,
  Seasons,
  Suitability,
  User,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

// Все запросы — с cookie сессии; изменяющие запросы несут заголовок против CSRF (проверяется бэкендом).
const BASE_HEADERS = { "Content-Type": "application/json", "X-Requested-With": "agro" };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`/api${path}`, { credentials: "same-origin", ...init, headers: { ...BASE_HEADERS, ...(init?.headers ?? {}) } });
  } catch {
    throw new ApiError(0, "network");
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = (await resp.json()) as { detail?: unknown };
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* тело не JSON */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

const post = <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const put = <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) });
const del = (path: string) => request<void>(path, { method: "DELETE" });

async function download(path: string, fallbackName: string): Promise<void> {
  const resp = await fetch(`/api${path}`, { credentials: "same-origin" });
  if (!resp.ok) throw new ApiError(resp.status, await resp.text());
  const blob = await resp.blob();
  const name = /filename="([^"]+)"/.exec(resp.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export const api = {
  health: () => request<{ status: string; offline: boolean; earthdata: boolean; demo: boolean }>("/health"),
  config: () => request<AppConfig>("/config"),
  demo: () => request<DemoField>("/demo"),
  analyze: (req: FieldRequest) => post<Analysis>("/field/analyze", req),
  compare: (req: CompareRequest) => post<Comparison>("/rotations/compare", req),
  job: (id: string) => request<Job>(`/jobs/${encodeURIComponent(id)}`),
  layer: (kind: string, bbox: number[], date?: string) =>
    request<LayerResponse>(`/layers/${kind}?bbox=${bbox.join(",")}${date ? `&date=${date}` : ""}`),
  rules: () => request<RulesCatalog>("/rules"),
  landing: () => request<{ facts: Record<string, LandingFact> }>("/content/landing"),
  retro: () => request<{ fields: RetroField[] }>("/retro"),
  retroSubmit: (body: unknown) => post<{ status: string; id: string }>("/retro/submissions", body),
  async reportPdf(req: ReportRequest): Promise<Blob> {
    const resp = await fetch("/api/report/pdf", { method: "POST", headers: BASE_HEADERS, body: JSON.stringify(req) });
    if (!resp.ok) throw new ApiError(resp.status, await resp.text());
    return resp.blob();
  },

  // учётные записи
  me: () => request<User>("/auth/me"),
  register: (body: { email: string; password: string; name: string; farm_name: string; lang: Lang }) => post<User>("/auth/register", body),
  login: (email: string, password: string) => post<User>("/auth/login", { email, password }),
  logout: () => post<{ status: string }>("/auth/logout"),
  demoLogin: (lang: Lang) => post<User>(`/auth/demo?lang=${lang}`),
  updateProfile: (body: { name: string; farm_name: string; lang: Lang }) => put<User>("/auth/me", body),

  // поля
  fields: () => request<{ fields: FieldRecord[] }>("/fields"),
  field: (id: number) => request<FieldRecord>(`/fields/${id}`),
  createField: (body: FieldInput) => post<FieldRecord>("/fields", body),
  updateField: (id: number, body: FieldInput) => put<FieldRecord>(`/fields/${id}`, body),
  deleteField: (id: number) => del(`/fields/${id}`),
  fieldOverview: (id: number) => request<Analysis>(`/fields/${id}/overview`),
  fieldMonitoring: (id: number, start?: string, end?: string) =>
    request<Monitoring>(`/fields/${id}/monitoring${start || end ? `?${new URLSearchParams({ ...(start ? { start } : {}), ...(end ? { end } : {}) })}` : ""}`),
  fieldSeasons: (id: number) => request<Seasons>(`/fields/${id}/seasons`),
  fieldRisk: (id: number) => request<Risk>(`/fields/${id}/risk`),
  fieldSuitability: (id: number) => request<Suitability>(`/fields/${id}/suitability`),
  fieldLayer: (id: number, kind: string, date?: string) => request<LayerResponse>(`/fields/${id}/layers/${kind}${date ? `?date=${date}` : ""}`),
  async fieldBareSoil(id: number, startYear?: number, endYear?: number): Promise<BareSoil> {
    if (import.meta.env.VITE_USE_MOCKS === "1") {
      await new Promise((r) => setTimeout(r, 600));
      const { mockBareSoil } = await import("./mocks/bareSoil");
      return mockBareSoil(id, startYear, endYear);
    }
    const q = new URLSearchParams();
    if (startYear !== undefined) q.set("start_year", String(startYear));
    if (endYear !== undefined) q.set("end_year", String(endYear));
    const qs = q.toString();
    return request<BareSoil>(`/fields/${id}/bare-soil${qs ? `?${qs}` : ""}`);
  },

  // анализы
  recentAnalyses: (limit = 10) => request<{ analyses: AnalysisListItem[] }>(`/analyses?limit=${limit}`),
  fieldAnalyses: (fieldId: number) => request<{ analyses: AnalysisListItem[] }>(`/fields/${fieldId}/analyses`),
  createAnalysis: (fieldId: number, body: AnalysisInput) => post<SavedAnalysis>(`/fields/${fieldId}/analyses`, body),
  analysis: (id: number) => request<SavedAnalysis>(`/analyses/${id}`),
  deleteAnalysis: (id: number) => del(`/analyses/${id}`),

  // экспорт
  downloadPdf: (fieldId: number, lang: Lang, analysisId?: number, variant?: string) =>
    download(`/fields/${fieldId}/report.pdf?${new URLSearchParams({ lang, ...(analysisId ? { analysis_id: String(analysisId) } : {}), ...(variant ? { variant } : {}) })}`, "report.pdf"),
  downloadXlsx: (fieldId: number, lang: Lang, analysisId?: number) =>
    download(`/fields/${fieldId}/report.xlsx?${new URLSearchParams({ lang, ...(analysisId ? { analysis_id: String(analysisId) } : {}) })}`, "report.xlsx"),
};

export interface RetroField {
  id: string;
  name: string;
  region: string;
  geometry: FieldRequest["geometry"];
  history: { year: number; crop: string }[];
  evidence: string;
}
