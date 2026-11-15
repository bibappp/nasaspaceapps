import type { Polygon } from "geojson";

const R = 6_371_008.8;
const rad = (d: number) => (d * Math.PI) / 180;

function ringArea(coords: number[][]): number {
  let total = 0;
  for (let i = 0; i < coords.length - 1; i++) {
    const [lon1 = 0, lat1 = 0] = coords[i] ?? [];
    const [lon2 = 0, lat2 = 0] = coords[i + 1] ?? [];
    total += rad(lon2 - lon1) * (2 + Math.sin(rad(lat1)) + Math.sin(rad(lat2)));
  }
  return (Math.abs(total) * R * R) / 2;
}

/** Площадь многоугольника на сфере, га (та же формула, что на бэкенде). */
export function areaHa(p: Polygon): number {
  const [outer, ...holes] = p.coordinates;
  if (!outer) return 0;
  return (ringArea(outer) - holes.reduce((s, h) => s + ringArea(h), 0)) / 10_000;
}

/** Достаёт один многоугольник из GeoJSON (Polygon, Feature, FeatureCollection, MultiPolygon из 1 части). */
export function extractPolygon(obj: unknown): Polygon | null {
  if (!obj || typeof obj !== "object") return null;
  const o = obj as { type?: string; geometry?: unknown; features?: unknown[]; coordinates?: unknown };
  if (o.type === "Feature") return extractPolygon(o.geometry);
  if (o.type === "FeatureCollection") {
    for (const f of o.features ?? []) {
      const p = extractPolygon(f);
      if (p) return p;
    }
    return null;
  }
  if (o.type === "MultiPolygon" && Array.isArray(o.coordinates) && o.coordinates.length === 1) {
    return { type: "Polygon", coordinates: (o.coordinates[0] as number[][][]).map((r) => r.map((c) => [c[0] ?? 0, c[1] ?? 0])) };
  }
  if (o.type === "Polygon" && Array.isArray(o.coordinates)) {
    return { type: "Polygon", coordinates: (o.coordinates as number[][][]).map((r) => r.map((c) => [c[0] ?? 0, c[1] ?? 0])) };
  }
  return null;
}

export function bboxOf(p: Polygon): [number, number, number, number] {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (const [x = 0, y = 0] of p.coordinates[0] ?? []) {
    minx = Math.min(minx, x); maxx = Math.max(maxx, x);
    miny = Math.min(miny, y); maxy = Math.max(maxy, y);
  }
  return [minx, miny, maxx, maxy];
}
