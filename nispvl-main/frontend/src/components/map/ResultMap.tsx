import type { Feature, Polygon } from "geojson";
import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { GeoJSON, MapContainer, useMap } from "react-leaflet";
import { api } from "../../api/client";
import type { Lang, LayerResponse } from "../../api/types";
import { RAMPS } from "../../lib/colors";
import { fmtNum } from "../../lib/format";
import Spinner from "../common/Spinner";
import { BaseLayers, OfflineNote, useOfflineBasemap } from "./BaseLayers";

type Kind = "ndvi" | "soil_moisture" | "precip";
const KINDS: Kind[] = ["ndvi", "soil_moisture", "precip"];

function FitTo({ layer, field }: { layer: LayerResponse | null; field: Polygon }) {
  const map = useMap();
  useEffect(() => {
    const target = layer
      ? L.geoJSON(layer as unknown as GeoJSON.FeatureCollection).getBounds()
      : L.geoJSON(field as unknown as GeoJSON.Geometry).getBounds();
    map.fitBounds(target, { padding: [20, 20], maxZoom: 15 });
  }, [layer?.meta.kind, layer?.meta.source, field, map]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function unitLabel(meta: LayerResponse["meta"], t: (k: string) => string) {
  if (meta.kind === "ndvi") return t("result.map.ndvi_unit");
  if (meta.kind === "precip") return t("result.map.precip_unit");
  return meta.fallback_for ? "GWETROOT 0–1" : t("result.map.sm_unit");
}

function Legend({ meta, lang }: { meta: LayerResponse["meta"]; lang: Lang }) {
  const { t } = useTranslation();
  const ramp = RAMPS[meta.kind] ?? RAMPS.ndvi!;
  const stops = Array.from({ length: 6 }, (_, i) => i / 5);
  const digits = meta.kind === "precip" ? 0 : 2;
  return (
    <div className="space-y-2 text-sm">
      <div className="font-semibold">{t("result.map.legend")}: {unitLabel(meta, t)}</div>
      <div className="h-3 w-full max-w-sm rounded" style={{ background: `linear-gradient(to right, ${stops.map((s) => ramp(s)).join(",")})` }} />
      <div className="flex max-w-sm justify-between text-xs text-ink-2">
        <span>{fmtNum(meta.legend.min, digits)}</span>
        <span>{fmtNum((meta.legend.min + meta.legend.max) / 2, digits)}</span>
        <span>{fmtNum(meta.legend.max, digits)}</span>
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="inline-block h-3 w-5 border-2 border-dashed border-line-strong bg-surface-sunken" /> {t("result.map.no_data")}
        <span className="ml-3 inline-block h-3 w-5 border-[3px] border-wheat-300" /> {t("result.map.field")}
      </div>
      <p className="rounded-lg bg-amber-50 px-3 py-2 text-amber-950">
        <b>{t("result.map.resolution")}:</b> {meta.spatial_resolution[lang]}
      </p>
      {meta.fallback_for && <p className="rounded-lg bg-amber-50 px-3 py-2 text-amber-950">{t("result.map.sm_fallback")}</p>}
      {meta.kind === "precip" && <p className="text-ink-2">{t("result.map.precip_note")}</p>}
      <p className="text-xs text-ink-muted">{meta.source_title}</p>
    </div>
  );
}

export default function ResultMap({ field, bbox }: { field: Polygon; bbox: [number, number, number, number] }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const [kind, setKind] = useState<Kind>("ndvi");
  const [date, setDate] = useState<string | undefined>();
  const [layer, setLayer] = useState<LayerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { offline, markOffline } = useOfflineBasemap();

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .layer(kind, bbox, date)
      .then((l) => alive && setLayer(l))
      .catch((e: Error) => {
        if (!alive) return;
        setLayer(null);
        setError(e.message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [kind, date, bbox]);

  const ramp = RAMPS[kind] ?? RAMPS.ndvi!;
  const style = useMemo(
    () => (f?: Feature) => {
      const p = (f?.properties ?? {}) as { value: number | null; in_field: boolean };
      if (!layer || p.value === null) {
        return { color: "#777", weight: 1, dashArray: "3 3", fillColor: "#ddd", fillOpacity: 0.5 };
      }
      const { min, max } = layer.meta.legend;
      const fill = ramp((p.value - min) / (max - min));
      const inField = kind !== "ndvi" || p.in_field;
      return { color: "#ffffff", weight: 0.6, fillColor: fill, fillOpacity: inField ? 0.85 : 0.4 };
    },
    [layer, kind, ramp],
  );

  const onEach = (f: Feature, l: L.Layer) => {
    const v = (f.properties as { value: number | null }).value;
    l.bindTooltip(v === null ? t("result.map.no_data") : fmtNum(v, kind === "precip" ? 0 : 3), { sticky: true });
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
      <div>
        <div className="mb-3 flex flex-wrap gap-2" role="tablist">
          {KINDS.map((k) => (
            <button
              key={k}
              role="tab"
              aria-selected={kind === k}
              className={kind === k ? "btn-primary" : "btn-secondary"}
              onClick={() => {
                setKind(k);
                setDate(undefined);
              }}
            >
              {t(`result.map.layers.${k}`)}
            </button>
          ))}
        </div>
        <MapContainer center={[51.7, 70.9]} zoom={12} className="h-[420px] w-full rounded-lg">
          <BaseLayers onOffline={markOffline} />
          {layer && (
            <GeoJSON
              key={`${layer.meta.kind}-${layer.meta.date}`}
              data={layer as unknown as GeoJSON.FeatureCollection}
              style={style}
              onEachFeature={onEach}
            />
          )}
          <GeoJSON key="field" data={field as unknown as GeoJSON.Geometry} style={{ color: "#f1d27a", weight: 3, fill: false }} interactive={false} />
          <FitTo layer={layer} field={field} />
        </MapContainer>
        {offline && <OfflineNote />}
      </div>
      <div className="space-y-3">
        {loading && <Spinner label={t("result.map.loading")} />}
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">{t("result.map.unavailable", { detail: error })}</p>}
        {layer && (
          <>
            <label className="block">
              <span className="label">{t("result.map.date")}</span>
              <select className="input" value={layer.meta.date} onChange={(e) => setDate(e.target.value)}>
                {[...layer.meta.dates].reverse().map((d) => (
                  <option key={d} value={d}>
                    {kind === "ndvi" ? d : d.slice(0, 4)}
                  </option>
                ))}
              </select>
            </label>
            <Legend meta={layer.meta} lang={lang} />
          </>
        )}
      </div>
    </div>
  );
}
