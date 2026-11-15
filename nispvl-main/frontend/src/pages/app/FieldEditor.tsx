import type { Polygon } from "geojson";
import { Plus, Trash2, Upload } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { FieldInput, HistoryItem, Lang, SoilInfo } from "../../api/types";
import FieldDrawMap from "../../components/map/FieldDrawMap";
import { ErrorBox, Loading, Notice, PageHeader } from "../../components/ui/ui";
import { readContourFile } from "../../components/wizard/StepField";
import { errorText } from "../../lib/async";
import { useConfig } from "../../lib/config";
import { fmtNum } from "../../lib/format";
import { areaHa } from "../../lib/geo";

const TEXTURES: NonNullable<SoilInfo["texture"]>[] = ["sand", "sandy_loam", "loam", "clay_loam", "clay"];
const EMPTY_SOIL: SoilInfo = { humus_pct: null, ph: null, texture: null, soil_type: "", survey_year: null, notes: "" };

function defaultHistory(): HistoryItem[] {
  const y = new Date().getFullYear();
  return [4, 3, 2, 1, 0].map((d) => ({ year: y - d, crop: "wheat" }));
}

const numOrNull = (s: string) => (s.trim() === "" ? null : Number(s.replace(",", ".")));

export default function FieldEditor() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { id } = useParams();
  const editing = id !== undefined;
  const navigate = useNavigate();
  const { config } = useConfig();
  const [form, setForm] = useState<FieldInput | null>(
    editing ? null : { name: "", region: "akmola", geometry: null as unknown as Polygon, history: defaultHistory(), history_is_scenario: false, soil: EMPTY_SOIL, notes: "" },
  );
  const [error, setError] = useState<string | null>(null);
  const [fileError, setFileError] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!editing) return;
    api
      .field(Number(id))
      .then((f) => setForm({ name: f.name, region: f.region, geometry: f.geometry, history: f.history, history_is_scenario: f.history_is_scenario, soil: { ...EMPTY_SOIL, ...f.soil }, notes: f.notes }))
      .catch((e: unknown) => setError(errorText(e, t)));
  }, [editing, id, t]);

  if (!form) return error ? <ErrorBox message={error} /> : <Loading />;
  const set = <K extends keyof FieldInput>(k: K, v: FieldInput[K]) => setForm({ ...form, [k]: v });
  const setSoil = <K extends keyof SoilInfo>(k: K, v: SoilInfo[K]) => setForm({ ...form, soil: { ...form.soil, [k]: v } });
  const area = form.geometry ? areaHa(form.geometry) : 0;
  const geomOk = !!form.geometry && area > 0.01 && area <= 50000;
  const years = form.history.map((h) => h.year);
  const historyOk = new Set(years).size === years.length;
  const maxHistory = config?.history.max_years ?? 10;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!geomOk || !historyOk) return;
    setBusy(true);
    setError(null);
    try {
      const body = { ...form, history: [...form.history].sort((a, b) => a.year - b.year) };
      const saved = editing ? await api.updateField(Number(id), body) : await api.createField(body);
      navigate(`/app/fields/${saved.id}`);
    } catch (err) {
      setError(errorText(err, t));
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!editing || !window.confirm(t("fields.delete_confirm", { name: form.name }))) return;
    setBusy(true);
    try {
      await api.deleteField(Number(id));
      navigate("/app/fields");
    } catch (err) {
      setError(errorText(err, t));
      setBusy(false);
    }
  };
  const onFile = async (file: File | undefined) => {
    if (!file) return;
    const p = await readContourFile(file);
    setFileError(!p);
    if (p) set("geometry", p);
  };

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-6">
      <PageHeader
        title={editing ? t("fields.edit_title", { name: form.name }) : t("fields.new_title")}
        subtitle={t("fields.editor_subtitle")}
        actions={
          <>
            <Link to={editing ? `/app/fields/${id}` : "/app/fields"} className="btn-secondary no-underline">{t("app.cancel")}</Link>
            <button type="submit" className="btn-primary" disabled={busy || !geomOk || !historyOk || !form.name.trim()}>
              {t("app.save")}
            </button>
          </>
        }
      />
      {error && <ErrorBox message={error} />}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section className="panel">
          <div className="panel-head">
            <h2 className="h3">{t("fields.boundary")}</h2>
            <span className={`text-sm tabular-nums ${geomOk ? "text-ink" : "text-ink-muted"}`}>
              {form.geometry ? `${fmtNum(area, 1)} ${t("units.ha")}` : t("wizard.field.no_field")}
            </span>
          </div>
          <div className="panel-body space-y-3">
            <p className="text-sm text-ink-muted">{t("wizard.field.hint")}</p>
            <FieldDrawMap geometry={form.geometry} onChange={(p) => set("geometry", p as Polygon)} />
            <div className="flex flex-wrap items-center gap-2">
              <label className="btn-secondary cursor-pointer">
                <Upload className="h-4 w-4" /> {t("wizard.field.upload")}
                <input type="file" accept=".geojson,.json,.kml" className="sr-only" onChange={(e) => void onFile(e.target.files?.[0])} />
              </label>
              {fileError && <span className="text-sm text-status-bad">{t("wizard.field.upload_error")}</span>}
              {form.geometry && area > 50000 && <span className="text-sm text-status-bad">{t("wizard.field.too_big")}</span>}
            </div>
          </div>
        </section>

        <div className="space-y-6">
          <section className="panel">
            <div className="panel-head"><h2 className="h3">{t("fields.general")}</h2></div>
            <div className="panel-body space-y-4">
              <label className="block">
                <span className="label">{t("fields.name")}</span>
                <input className="input" required maxLength={80} value={form.name} onChange={(e) => set("name", e.target.value)} placeholder={t("fields.name_placeholder")} />
              </label>
              <label className="block">
                <span className="label">{t("wizard.field.region")}</span>
                <select className="input" value={form.region} onChange={(e) => set("region", e.target.value)}>
                  {config?.regions.map((r) => (
                    <option key={r.id} value={r.id}>{r.name[lang]}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="label">{t("fields.notes")}</span>
                <textarea className="input h-24 py-2" maxLength={4000} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
              </label>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2 className="h3">{t("fields.history")}</h2>
              <button
                type="button"
                className="btn-ghost h-8"
                disabled={form.history.length >= maxHistory}
                onClick={() => {
                  const minYear = Math.min(...years, new Date().getFullYear() + 1);
                  set("history", [{ year: minYear - 1, crop: "wheat" }, ...form.history]);
                }}
              >
                <Plus className="h-4 w-4" /> {t("wizard.history.add")}
              </button>
            </div>
            <div className="panel-body space-y-3">
              <p className="text-sm text-ink-muted">{t("wizard.history.hint")}</p>
              <div className="space-y-2">
                {form.history.map((h, i) => (
                  <div key={i} className="flex gap-2">
                    <input
                      className="input w-24"
                      type="number"
                      min={1990}
                      max={2100}
                      aria-label={t("wizard.history.year")}
                      value={h.year}
                      onChange={(e) => set("history", form.history.map((x, j) => (j === i ? { ...x, year: Number(e.target.value) } : x)))}
                    />
                    <select
                      className="input flex-1"
                      aria-label={t("wizard.history.crop")}
                      value={h.crop}
                      onChange={(e) => set("history", form.history.map((x, j) => (j === i ? { ...x, crop: e.target.value } : x)))}
                    >
                      {config?.crops.map((c) => (
                        <option key={c.id} value={c.id}>{c.name[lang]}</option>
                      ))}
                    </select>
                    <button type="button" className="btn-icon btn-ghost" aria-label={t("wizard.history.remove")} onClick={() => set("history", form.history.filter((_, j) => j !== i))}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
              {!historyOk && <p className="text-sm text-status-bad">{t("fields.history_duplicate")}</p>}
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={form.history_is_scenario} onChange={(e) => set("history_is_scenario", e.target.checked)} />
                <span>
                  {t("fields.history_is_scenario")}
                  <span className="hint block">{t("fields.history_is_scenario_hint")}</span>
                </span>
              </label>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head"><h2 className="h3">{t("fields.soil")}</h2></div>
            <div className="panel-body space-y-4">
              <Notice>{t("fields.soil_hint")}</Notice>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="label">{t("fields.humus")}</span>
                  <input className="input" inputMode="decimal" value={form.soil.humus_pct ?? ""} onChange={(e) => setSoil("humus_pct", numOrNull(e.target.value))} />
                </label>
                <label className="block">
                  <span className="label">pH</span>
                  <input className="input" inputMode="decimal" value={form.soil.ph ?? ""} onChange={(e) => setSoil("ph", numOrNull(e.target.value))} />
                </label>
                <label className="block">
                  <span className="label">{t("fields.texture")}</span>
                  <select className="input" value={form.soil.texture ?? ""} onChange={(e) => setSoil("texture", (e.target.value || null) as SoilInfo["texture"])}>
                    <option value="">—</option>
                    {TEXTURES.map((x) => (
                      <option key={x} value={x}>{t(`fields.textures.${x}`)}</option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="label">{t("fields.survey_year")}</span>
                  <input className="input" type="number" min={1950} max={2100} value={form.soil.survey_year ?? ""} onChange={(e) => setSoil("survey_year", numOrNull(e.target.value))} />
                </label>
              </div>
              <label className="block">
                <span className="label">{t("fields.soil_type")}</span>
                <input className="input" maxLength={120} value={form.soil.soil_type} onChange={(e) => setSoil("soil_type", e.target.value)} placeholder={t("fields.soil_type_placeholder")} />
              </label>
              <label className="block">
                <span className="label">{t("fields.soil_notes")}</span>
                <input className="input" maxLength={1000} value={form.soil.notes} onChange={(e) => setSoil("notes", e.target.value)} />
              </label>
            </div>
          </section>

          {editing && (
            <section className="panel border-red-200">
              <div className="panel-body flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="h3">{t("fields.delete")}</div>
                  <p className="text-sm text-ink-muted">{t("fields.delete_hint")}</p>
                </div>
                <button type="button" className="btn-danger" disabled={busy} onClick={() => void remove()}>
                  <Trash2 className="h-4 w-4" /> {t("fields.delete")}
                </button>
              </div>
            </section>
          )}
        </div>
      </div>
    </form>
  );
}
