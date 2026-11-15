import type { Feature, Polygon } from "geojson";
import L from "leaflet";
import { Columns2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { GeoJSON, MapContainer, useMap } from "react-leaflet";
import { api } from "../../api/client";
import type { Lang, LayerResponse } from "../../api/types";
import { RAMPS } from "../../lib/colors";
import { errorText } from "../../lib/async";
import { fmtNum } from "../../lib/format";
import { tx } from "../../lib/i18n-text";
import { BaseLayers, OfflineNote, useOfflineBasemap } from "../map/BaseLayers";
import { ErrorBox, KindBadge, Loading, Notice } from "../ui/ui";

type Kind = "ndvi" | "ndvi_anomaly" | "soil_moisture" | "precip";
const KINDS: Kind[] = ["ndvi", "ndvi_anomaly", "soil_moisture", "precip"];

// расходящаяся шкала для аномалии NDVI: коричневый — ниже медианы, серый — около нуля, зелёный — выше
const DIVERGING = (t: number): string => {
  const x = Math.min(1, Math.max(0, t));
  const lo = [140, 81, 10], mid = [226, 226, 222], hi = [31, 120, 60];
  const [a, b, k] = x < 0.5 ? [lo, mid, x / 0.5] : [mid, hi, (x - 0.5) / 0.5];
  return `rgb(${a.map((v, i) => Math.round(v + ((b[i] ?? v) - v) * k)).join(",")})`;
};
const rampFor = (kind: string) => (kind === "ndvi_anomaly" ? DIVERGING : RAMPS[kind] ?? RAMPS.ndvi!);

function Fit({ field }: { field: Polygon }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(L.geoJSON(field as unknown as GeoJSON.Geometry).getBounds().pad(0.6), { maxZoom: 15 });
  }, [field, map]);
  return null;
}

function useLayer(fieldId: number, kind: Kind, date: string | undefined, enabled = true) {
  const [layer, setLayer] = useState<LayerResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .fieldLayer(fieldId, kind, date)
      .then((l) => alive && setLayer(l))
      .catch((e: unknown) => {
        if (alive) {
          setLayer(null);
          setError(e);
        }
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [fieldId, kind, date, enabled]);
  return { layer, error, loading };
}

function LayerMap({ field, layer, height }: { field: Polygon; layer: LayerResponse | null; height: string }) {
  const { t } = useTranslation();
  const { offline, markOffline } = useOfflineBasemap();
  const kind = layer?.meta.kind ?? "ndvi";
  const ramp = rampFor(kind);
  const style = useMemo(
    () => (f?: Feature) => {
      const p = (f?.properties ?? {}) as { value: number | null; in_field: boolean };
      if (!layer || p.value === null) return { color: "#8A929C", weight: 0.8, dashArray: "3 3", fillColor: "#E3E6EA", fillOpacity: 0.5 };
      const { min, max } = layer.meta.legend;
      return { color: "#ffffff", weight: 0.5, fillColor: ramp((p.value - min) / (max - min || 1)), fillOpacity: p.in_field || kind === "precip" || kind === "soil_moisture" ? 0.85 : 0.35 };
    },
    [layer, kind, ramp],
  );
  const digits = kind === "precip" ? 0 : 3;
  return (
    <div>
      <MapContainer center={[52, 68]} zoom={12} style={{ height }} className="w-full rounded-md border border-line">
        <BaseLayers onOffline={markOffline} />
        {layer && (
          <GeoJSON
            key={`${layer.meta.kind}-${layer.meta.date}`}
            data={layer as unknown as GeoJSON.FeatureCollection}
            style={style}
            onEachFeature={(f: Feature, l: L.Layer) => {
              const v = (f.properties as { value: number | null }).value;
              l.bindTooltip(v === null ? t("result.map.no_data") : `${fmtNum(v, digits)} ${layer.meta.unit}`, { sticky: true });
            }}
          />
        )}
        <GeoJSON key="field" data={field as unknown as GeoJSON.Geometry} style={{ color: "#EBCB7C", weight: 2.5, fill: false }} interactive={false} />
        <Fit field={field} />
      </MapContainer>
      {offline && <OfflineNote />}
    </div>
  );
}

function Legend({ meta }: { meta: LayerResponse["meta"] }) {
  const { t } = useTranslation();
  const ramp = rampFor(meta.kind);
  const stops = Array.from({ length: 7 }, (_, i) => i / 6);
  const digits = meta.kind === "precip" ? 0 : 2;
  return (
    <div className="space-y-1.5">
      <div className="text-xs font-medium text-ink-2">{t(`fieldmap.unit.${meta.kind}`, { defaultValue: meta.unit })}</div>
      <div className="h-2.5 w-full rounded-sm" style={{ background: `linear-gradient(to right, ${stops.map((s) => ramp(s)).join(",")})` }} />
      <div className="flex justify-between text-xs tabular-nums text-ink-muted">
        <span>{fmtNum(meta.legend.min, digits)}</span>
        <span>{fmtNum((meta.legend.min + meta.legend.max) / 2, digits)}</span>
        <span>{fmtNum(meta.legend.max, digits)}</span>
      </div>
      <div className="flex flex-wrap items-center gap-3 pt-1 text-xs text-ink-muted">
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-4 border border-dashed border-ink-subtle bg-line" /> {t("result.map.no_data")}</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-4 border-2 border-wheat-300" /> {t("result.map.field")}</span>
      </div>
    </div>
  );
}

function Summary({ layer }: { layer: LayerResponse }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const m = layer.meta as LayerResponse["meta"] & { summary?: { field_mean: number | null; cells_in_field: number; cells_with_data: number; coarser_than_field: boolean }; reference_dates?: string[] };
  const s = m.summary;
  return (
    <div className="space-y-3 text-sm">
      {s && (
        <div className="rounded-md bg-surface px-3 py-2.5">
          <div className="text-xs text-ink-muted">{t("fieldmap.field_mean")}</div>
          <div className="text-lg font-semibold tabular-nums">{s.field_mean === null ? "—" : `${fmtNum(s.field_mean, m.kind === "precip" ? 0 : 3)} ${m.unit}`}</div>
          <div className="text-xs text-ink-muted">{t("fieldmap.cells", { n: s.cells_with_data, total: s.cells_in_field })}</div>
        </div>
      )}
      {s?.coarser_than_field && <Notice tone="warn">{t("fieldmap.coarser")}</Notice>}
      <div className="text-xs leading-relaxed text-ink-muted">
        <b className="text-ink-2">{t("result.map.resolution")}:</b> {tx(m.spatial_resolution, lang)}
      </div>
      {m.fallback_for && <Notice tone="warn">{t("result.map.sm_fallback")}</Notice>}
      {m.kind === "ndvi_anomaly" && <p className="text-xs text-ink-muted">{t("fieldmap.anomaly_note", { dates: (m.reference_dates ?? []).join(", ") || "—" })}</p>}
      {m.kind === "precip" && <p className="text-xs text-ink-muted">{t("result.map.precip_note")}</p>}
      <div className="flex items-center gap-2 text-xs text-ink-muted">
        <KindBadge kind={m.kind === "precip" || m.fallback_for ? "reanalysis" : "observation"} /> {m.source_title}
      </div>
    </div>
  );
}

function DateSelect({ layer, value, onChange, label }: { layer: LayerResponse | null; value: string | undefined; onChange: (d: string) => void; label: string }) {
  if (!layer) return null;
  const kind = layer.meta.kind;
  return (
    <label className="block">
      <span className="label">{label}</span>
      <select className="input" value={value ?? layer.meta.date} onChange={(e) => onChange(e.target.value)}>
        {[...layer.meta.dates].reverse().map((d) => (
          <option key={d} value={d}>{kind === "ndvi" || kind === "ndvi_anomaly" || kind === "soil_moisture" ? d : d.slice(0, 4)}</option>
        ))}
      </select>
    </label>
  );
}

export default function FieldMap({ fieldId, geometry }: { fieldId: number; geometry: Polygon }) {
  const { t } = useTranslation();
  const [kind, setKind] = useState<Kind>("ndvi");
  const [dateA, setDateA] = useState<string | undefined>();
  const [dateB, setDateB] = useState<string | undefined>();
  const [compare, setCompare] = useState(false);
  const a = useLayer(fieldId, kind, dateA);
  const b = useLayer(fieldId, kind, dateB ?? a.layer?.meta.dates.at(-2), compare && !!a.layer);
  const changeKind = (k: Kind) => {
    setKind(k);
    setDateA(undefined);
    setDateB(undefined);
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-md border border-line-strong bg-white p-0.5" role="tablist">
          {KINDS.map((k) => (
            <button key={k} type="button" role="tab" aria-selected={kind === k} onClick={() => changeKind(k)} className={`h-8 rounded px-3 text-sm font-medium ${kind === k ? "bg-field-700 text-white" : "text-ink-2 hover:text-ink"}`}>
              {t(`fieldmap.layer.${k}`)}
            </button>
          ))}
        </div>
        <button type="button" className={compare ? "btn-primary h-9" : "btn-secondary h-9"} aria-pressed={compare} onClick={() => setCompare((c) => !c)}>
          <Columns2 className="h-4 w-4" /> {t("fieldmap.compare")}
        </button>
      </div>

      <div className={`grid gap-4 ${compare ? "lg:grid-cols-2" : "lg:grid-cols-[minmax(0,1fr)_300px]"}`}>
        {[{ s: a, date: dateA, set: setDateA, label: compare ? t("fieldmap.date_a") : t("result.map.date") }, ...(compare ? [{ s: b, date: dateB, set: setDateB, label: t("fieldmap.date_b") }] : [])].map(({ s, date, set, label }, i) => (
          <div key={i} className="panel">
            <div className="panel-body space-y-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="w-48"><DateSelect layer={s.layer} value={date} onChange={set} label={label} /></div>
                {s.loading && <Loading label={t("result.map.loading")} />}
              </div>
              {s.error ? <ErrorBox message={t("result.map.unavailable", { detail: errorText(s.error, t) })} /> : null}
              <LayerMap field={geometry} layer={s.layer} height={compare ? "380px" : "460px"} />
              {compare && s.layer && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Legend meta={s.layer.meta} />
                  <Summary layer={s.layer} />
                </div>
              )}
            </div>
          </div>
        ))}
        {!compare && a.layer && (
          <div className="panel">
            <div className="panel-body space-y-4">
              <Legend meta={a.layer.meta} />
              <Summary layer={a.layer} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
