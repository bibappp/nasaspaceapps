import type { Polygon } from "geojson";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type RetroField } from "../api/client";
import type { Analysis, HistoryItem, Lang } from "../api/types";
import Spinner from "../components/common/Spinner";
import { readContourFile } from "../components/wizard/StepField";
import { useConfig, useCropName } from "../lib/config";
import { fmtNum } from "../lib/format";

const LEGUME_FILL = "#c5dbae";

function VerifiedField({ field }: { field: RetroField }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const cropName = useCropName();
  const { config } = useConfig();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  useEffect(() => {
    api.analyze({ geometry: field.geometry, region: field.region, history: [], priority: "max_income", horizon_years: 4 }).then(setAnalysis).catch(() => setAnalysis(null));
  }, [field]);
  const group = (c: string) => config?.crops.find((x) => x.id === c)?.group;
  const crops = new Map(field.history.map((h) => [h.year, h.crop]));
  const rows = (analysis?.ndvi.trend?.yearly_max ?? []).map((r) => ({ year: r.year, ndvi: r.ndvi, crop: crops.get(r.year) }));
  return (
    <article className="card space-y-2">
      <h2 className="h3">{field.name}</h2>
      <p className="text-sm text-ink-2">{field.evidence}</p>
      {!analysis ? (
        <Spinner label={t("retro.loading_field")} />
      ) : (
        <figure>
          <figcaption className="font-semibold">{t("retro.chart")}</figcaption>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows}>
                <CartesianGrid stroke="#e5e5e0" vertical={false} />
                <XAxis dataKey="year" type="number" domain={["dataMin", "dataMax"]} tick={{ fontSize: 12 }} />
                <YAxis domain={[0, 1]} tick={{ fontSize: 12 }} width={40} />
                {field.history.filter((h) => group(h.crop) === "legume").map((h) => (
                  <ReferenceArea key={h.year} x1={h.year - 0.5} x2={h.year + 0.5} fill={LEGUME_FILL} fillOpacity={0.6} />
                ))}
                <Tooltip formatter={(v: number, _k, item) => [fmtNum(v, 3), cropName(String((item.payload as { crop?: string }).crop ?? ""), lang)]} />
                <Line dataKey="ndvi" stroke="#2a78d6" strokeWidth={2} dot={{ r: 5 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </figure>
      )}
      <ul className="flex flex-wrap gap-1 text-xs">
        {field.history.map((h) => (
          <li key={h.year} className={`rounded px-2 py-1 ${group(h.crop) === "legume" ? "bg-field-200" : "bg-surface-sunken"}`}>{h.year}: {cropName(h.crop, lang)}</li>
        ))}
      </ul>
    </article>
  );
}

function SubmitForm() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { config } = useConfig();
  const year = new Date().getFullYear();
  const [farm, setFarm] = useState("");
  const [contact, setContact] = useState("");
  const [region, setRegion] = useState("akmola");
  const [history, setHistory] = useState<HistoryItem[]>(() => [5, 4, 3, 2, 1].map((d) => ({ year: year - d, crop: "wheat" })));
  const [evidence, setEvidence] = useState("");
  const [geometry, setGeometry] = useState<Polygon | null>(null);
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<"idle" | "busy" | "sent" | "error">("idle");
  if (!config) return null;
  if (state === "sent") return <p className="card bg-surface font-semibold">{t("retro.sent")}</p>;
  return (
    <form
      className="card space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setState("busy");
        try {
          await api.retroSubmit({ farm_name: farm, contact, region, geometry, history, evidence, consent });
          setState("sent");
        } catch {
          setState("error");
        }
      }}
    >
      <h2 className="h2">{t("retro.form_title")}</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="block"><span className="label">{t("retro.farm")}</span><input className="input" required value={farm} onChange={(e) => setFarm(e.target.value)} /></label>
        <label className="block"><span className="label">{t("retro.contact")}</span><input className="input" required minLength={3} value={contact} onChange={(e) => setContact(e.target.value)} /></label>
        <label className="block">
          <span className="label">{t("retro.region")}</span>
          <select className="input" value={region} onChange={(e) => setRegion(e.target.value)}>
            {config.regions.map((r) => <option key={r.id} value={r.id}>{r.name[lang]}</option>)}
          </select>
        </label>
      </div>
      <fieldset>
        <legend className="label">{t("retro.history")}</legend>
        <div className="grid gap-2 sm:grid-cols-5">
          {history.map((h, i) => (
            <label key={h.year} className="block">
              <span className="text-sm font-semibold">{h.year}</span>
              <select className="input" value={h.crop} onChange={(e) => setHistory(history.map((x, j) => (j === i ? { ...x, crop: e.target.value } : x)))}>
                {config.crops.map((c) => <option key={c.id} value={c.id}>{c.name[lang]}</option>)}
              </select>
            </label>
          ))}
        </div>
      </fieldset>
      <label className="block"><span className="label">{t("retro.evidence")}</span><textarea className="input min-h-[90px]" value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
      <label className="block">
        <span className="label">{t("retro.geometry")}</span>
        <input type="file" accept=".geojson,.json,.kml" onChange={async (e) => { const f = e.target.files?.[0]; if (f) setGeometry(await readContourFile(f)); }} />
      </label>
      <label className="flex items-start gap-2"><input type="checkbox" className="mt-1 h-5 w-5 accent-field-700" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />{t("retro.consent")}</label>
      {state === "error" && <p className="text-red-800">{t("app.error")}</p>}
      <button className="btn-primary" disabled={state === "busy" || !consent}>{t("retro.submit")}</button>
    </form>
  );
}

export default function Retro() {
  const { t } = useTranslation();
  const [fields, setFields] = useState<RetroField[] | null>(null);
  useEffect(() => {
    api.retro().then((r) => setFields(r.fields)).catch(() => setFields([]));
  }, []);
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="h1">{t("retro.title")}</h1>
        <p className="text-lg">{t("retro.lead")}</p>
      </header>
      {fields === null ? (
        <Spinner label={t("app.loading")} />
      ) : fields.length === 0 ? (
        <div className="card space-y-2 border-amber-400 bg-amber-50">
          <p className="text-lg font-semibold">{t("retro.none")}</p>
          <p>{t("retro.none_hint")}</p>
        </div>
      ) : (
        fields.map((f) => <VerifiedField key={f.id} field={f} />)
      )}
      <SubmitForm />
    </div>
  );
}
