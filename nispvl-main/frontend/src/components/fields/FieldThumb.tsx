import type { Polygon } from "geojson";

/** Небольшой контур поля в SVG (без подложки) — для списков. */
export default function FieldThumb({ geometry, size = 40 }: { geometry: Polygon; size?: number }) {
  const ring = geometry.coordinates[0] ?? [];
  const xs = ring.map((p) => p[0] ?? 0);
  const ys = ring.map((p) => p[1] ?? 0);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const k = Math.cos(((y0 + y1) / 2) * (Math.PI / 180));
  const w = (x1 - x0) * k || 1;
  const h = y1 - y0 || 1;
  const s = (size - 6) / Math.max(w, h);
  const pts = ring.map(([x = 0, y = 0]) => `${3 + ((x - x0) * k * s + (size - 6 - w * s) / 2)},${3 + ((y1 - y) * s + (size - 6 - h * s) / 2)}`).join(" ");
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="flex-none rounded border border-line bg-field-50" aria-hidden>
      <polygon points={pts} fill="#C4DACB" stroke="#1F5134" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}
