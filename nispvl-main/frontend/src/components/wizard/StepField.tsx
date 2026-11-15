import { kml } from "@tmcw/togeojson";
import type { Polygon } from "geojson";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Lang } from "../../api/types";
import { useConfig } from "../../lib/config";
import { areaHa, extractPolygon } from "../../lib/geo";
import { fmtNum } from "../../lib/format";
import FieldDrawMap from "../map/FieldDrawMap";

export async function readContourFile(file: File): Promise<Polygon | null> {
  const text = await file.text();
  if (file.name.toLowerCase().endsWith(".kml") || text.trimStart().startsWith("<")) {
    const doc = new DOMParser().parseFromString(text, "text/xml");
    return extractPolygon(kml(doc));
  }
  try {
    return extractPolygon(JSON.parse(text));
  } catch {
    return null;
  }
}

interface Props {
  geometry: Polygon | null;
  region: string;
  onGeometry: (p: Polygon | null) => void;
  onRegion: (r: string) => void;
}

export default function StepField({ geometry, region, onGeometry, onRegion }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { config } = useConfig();
  const [uploadError, setUploadError] = useState(false);
  const area = geometry ? areaHa(geometry) : 0;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="h2">{t("wizard.field.title")}</h2>
        <p className="muted mt-1">{t("wizard.field.hint")}</p>
      </div>
      <FieldDrawMap geometry={geometry} onChange={onGeometry} />
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card">
          <div className="label">{t("wizard.field.area")}</div>
          {geometry ? (
            <div className="text-3xl font-semibold text-field-800">
              {fmtNum(area, 1)} <span className="text-lg">{t("wizard.field.ha")}</span>
            </div>
          ) : (
            <div className="text-ink-muted">{t("wizard.field.no_field")}</div>
          )}
          {area > 50000 && <p className="mt-1 text-sm text-red-800">{t("wizard.field.too_big")}</p>}
          {geometry && (
            <button type="button" className="btn-ghost mt-2 px-0" onClick={() => onGeometry(null)}>
              {t("wizard.field.clear")}
            </button>
          )}
        </div>
        <label className="card block">
          <span className="label">{t("wizard.field.region")}</span>
          <select className="input" value={region} onChange={(e) => onRegion(e.target.value)}>
            {config?.regions.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name[lang]}
              </option>
            ))}
          </select>
        </label>
        <label className="card block">
          <span className="label">{t("wizard.field.upload")}</span>
          <input
            type="file"
            accept=".geojson,.json,.kml,application/geo+json,application/vnd.google-earth.kml+xml"
            className="block w-full text-sm file:mr-3 file:min-h-[44px] file:rounded-xl file:border-0 file:bg-surface file:px-4 file:font-semibold file:text-field-800"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const p = await readContourFile(f);
              setUploadError(!p);
              if (p) onGeometry(p);
            }}
          />
          {uploadError && <p className="mt-2 text-sm text-red-800">{t("wizard.field.upload_error")}</p>}
        </label>
      </div>
      <p className="text-xs text-ink-muted">{t("wizard.field.attribution_note")}</p>
    </div>
  );
}
