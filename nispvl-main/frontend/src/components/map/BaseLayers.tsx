import { useState } from "react";
import { useTranslation } from "react-i18next";
import { LayersControl, TileLayer } from "react-leaflet";

/** Подложки OSM и Esri World Imagery. Если тайлы не грузятся (нет интернета) — сообщаем. */
export function BaseLayers({ defaultSatellite = true, onOffline }: { defaultSatellite?: boolean; onOffline: () => void }) {
  const { t } = useTranslation();
  const handlers = { tileerror: onOffline };
  return (
    <LayersControl position="topright">
      <LayersControl.BaseLayer checked={!defaultSatellite} name={t("wizard.field.basemap_osm")}>
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          maxZoom={19}
          eventHandlers={handlers}
        />
      </LayersControl.BaseLayer>
      <LayersControl.BaseLayer checked={defaultSatellite} name={t("wizard.field.basemap_sat")}>
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          attribution="Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
          maxZoom={18}
          eventHandlers={handlers}
        />
      </LayersControl.BaseLayer>
    </LayersControl>
  );
}

export function useOfflineBasemap() {
  const [offline, setOffline] = useState(false);
  return { offline, markOffline: () => setOffline(true) };
}

export function OfflineNote() {
  const { t } = useTranslation();
  return (
    <div className="mt-2 rounded-lg bg-surface-sunken px-3 py-2 text-sm text-ink-2" role="status">
      {t("wizard.field.basemap_offline")}
    </div>
  );
}
