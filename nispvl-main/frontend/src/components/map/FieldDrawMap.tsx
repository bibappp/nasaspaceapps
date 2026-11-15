import "../../lib/leaflet-global";
import "@geoman-io/leaflet-geoman-free";
import type { Polygon } from "geojson";
import L from "leaflet";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { MapContainer, useMap } from "react-leaflet";
import { BaseLayers, OfflineNote, useOfflineBasemap } from "./BaseLayers";

const FIELD_STYLE: L.PathOptions = { color: "#f1d27a", weight: 3, fillColor: "#f1d27a", fillOpacity: 0.15 };
const START: L.LatLngTuple = [52.3, 69.0];

function toPolygon(layer: L.Layer): Polygon | null {
  const gj = (layer as L.Polygon).toGeoJSON?.();
  if (!gj || gj.geometry.type !== "Polygon") return null;
  return gj.geometry as Polygon;
}

function Geoman({ geometry, onChange }: { geometry: Polygon | null; onChange: (p: Polygon | null) => void }) {
  const map = useMap();
  const { i18n } = useTranslation();
  const layerRef = useRef<L.Polygon | null>(null);
  const lastJson = useRef<string>("");
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const emit = (layer: L.Polygon) => {
    const p = toPolygon(layer);
    lastJson.current = JSON.stringify(p);
    onChangeRef.current(p);
  };
  const attachRef = useRef((layer: L.Polygon) => {
    layer.on("pm:edit", () => emit(layer));
  });

  useEffect(() => {
    map.pm.addControls({
      position: "topleft",
      drawMarker: false,
      drawCircleMarker: false,
      drawPolyline: false,
      drawCircle: false,
      drawText: false,
      cutPolygon: false,
      rotateMode: false,
      dragMode: false,
    });
    map.pm.setGlobalOptions({ pathOptions: FIELD_STYLE, snappable: true });

    const attach = attachRef.current;
    const onCreate = (e: { layer: L.Layer }) => {
      if (layerRef.current && layerRef.current !== e.layer) map.removeLayer(layerRef.current);
      const layer = e.layer as L.Polygon;
      layer.setStyle(FIELD_STYLE);
      layerRef.current = layer;
      attach(layer);
      emit(layer);
    };
    const onRemove = (e: { layer: L.Layer }) => {
      if (e.layer === layerRef.current) {
        layerRef.current = null;
        lastJson.current = "null";
        onChangeRef.current(null);
      }
    };
    map.on("pm:create", onCreate as L.LeafletEventHandlerFn);
    map.on("pm:remove", onRemove as L.LeafletEventHandlerFn);
    return () => {
      map.off("pm:create", onCreate as L.LeafletEventHandlerFn);
      map.off("pm:remove", onRemove as L.LeafletEventHandlerFn);
      map.pm.removeControls();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  useEffect(() => {
    // у Geoman есть русские подписи; казахских нет — используем русские
    map.pm.setLang("ru");
  }, [map, i18n.language]);

  // Внешнее изменение контура (демо, загрузка файла, «стереть»)
  useEffect(() => {
    const json = JSON.stringify(geometry);
    if (json === lastJson.current) return;
    lastJson.current = json;
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }
    if (!geometry) return;
    const layer = L.polygon(
      geometry.coordinates.map((ring) => ring.map(([x = 0, y = 0]) => [y, x] as L.LatLngTuple)),
      FIELD_STYLE,
    ).addTo(map);
    layerRef.current = layer;
    attachRef.current(layer);
    map.fitBounds(layer.getBounds(), { padding: [40, 40], maxZoom: 15 });
  }, [geometry, map]);

  return null;
}

function GoTo() {
  const map = useMap();
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const go = () => {
    const m = text.replace(/,(?=\d)/g, ".").match(/(-?\d+(?:\.\d+)?)[\s;,]+(-?\d+(?:\.\d+)?)/);
    if (m) map.setView([Number(m[1]), Number(m[2])], 14);
  };
  return (
    <div className="leaflet-bottom leaflet-left">
      {/* не <form>: карта бывает внутри формы редактора поля */}
      <div className="leaflet-control flex gap-1 rounded-md bg-white p-1 shadow">
        <input
          className="w-44 rounded border px-2 py-1 text-sm"
          placeholder="51.69, 70.93"
          aria-label={t("wizard.field.search_coords")}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              go();
            }
          }}
        />
        <button className="rounded bg-field-700 px-2 text-sm font-medium text-white" type="button" onClick={go}>
          {t("wizard.field.go")}
        </button>
      </div>
    </div>
  );
}

export default function FieldDrawMap({ geometry, onChange }: { geometry: Polygon | null; onChange: (p: Polygon | null) => void }) {
  const { offline, markOffline } = useOfflineBasemap();
  return (
    <div>
      <MapContainer center={START} zoom={6} className="h-[420px] w-full rounded-lg sm:h-[520px]" scrollWheelZoom>
        <BaseLayers onOffline={markOffline} />
        <Geoman geometry={geometry} onChange={onChange} />
        <GoTo />
      </MapContainer>
      {offline && <OfflineNote />}
    </div>
  );
}
