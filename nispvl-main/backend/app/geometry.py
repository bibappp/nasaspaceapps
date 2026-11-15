"""Работа с контуром поля: проверка, площадь, центроид, bbox."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from shapely.geometry import Polygon, shape
from shapely.validation import make_valid

EARTH_RADIUS_M = 6_371_008.8  # средний радиус (IUGG)
MAX_AREA_HA = 50_000.0


class GeometryError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    polygon: Polygon
    area_ha: float
    centroid_lon: float
    centroid_lat: float

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return self.polygon.bounds  # (minx, miny, maxx, maxy)

    def half_extent_km(self) -> tuple[float, float]:
        """Половина высоты и ширины bbox в км (для запроса окна MODIS)."""
        minx, miny, maxx, maxy = self.bbox
        km_ns = (maxy - miny) * math.pi / 180 * EARTH_RADIUS_M / 1000 / 2
        km_ew = (maxx - minx) * math.pi / 180 * EARTH_RADIUS_M * math.cos(math.radians(self.centroid_lat)) / 1000 / 2
        return km_ns, km_ew

    def geojson(self) -> dict:
        return {"type": "Polygon", "coordinates": [[list(c) for c in self.polygon.exterior.coords]]}

    def canonical(self) -> list[list[float]]:
        """Координаты, округлённые до 5 знаков (~1 м): основа ключа кэша."""
        return [[round(x, 5), round(y, 5)] for x, y in self.polygon.exterior.coords]


def _ring_area_m2(coords: list[tuple[float, float]]) -> float:
    """Площадь кольца на сфере (формула Chamberlain & Duquette, 2007), м²."""
    total = 0.0
    n = len(coords)
    for i in range(n - 1):
        lon1, lat1 = coords[i]
        lon2, lat2 = coords[i + 1]
        total += math.radians(lon2 - lon1) * (2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
    return abs(total) * EARTH_RADIUS_M**2 / 2


def geodesic_area_ha(polygon: Polygon) -> float:
    area = _ring_area_m2(list(polygon.exterior.coords))
    for ring in polygon.interiors:
        area -= _ring_area_m2(list(ring.coords))
    return area / 10_000


def parse_field(geometry: dict[str, Any]) -> Field:
    """Принимает GeoJSON Polygon (или Feature с Polygon), долгота/широта WGS84."""
    if not isinstance(geometry, dict):
        raise GeometryError("geometry must be a GeoJSON object")
    if geometry.get("type") == "Feature":
        geometry = geometry.get("geometry") or {}
    if geometry.get("type") == "FeatureCollection":
        feats = geometry.get("features") or []
        geometry = (feats[0].get("geometry") if feats else {}) or {}
    if geometry.get("type") == "MultiPolygon" and len(geometry.get("coordinates", [])) == 1:
        geometry = {"type": "Polygon", "coordinates": geometry["coordinates"][0]}
    if geometry.get("type") != "Polygon":
        raise GeometryError("only a single Polygon is supported")
    try:
        # KML даёт третью координату (высоту) — отбрасываем
        rings = [[(float(p[0]), float(p[1])) for p in ring] for ring in geometry["coordinates"]]
        poly = shape({"type": "Polygon", "coordinates": rings})
    except Exception as exc:
        raise GeometryError(f"invalid polygon: {exc}") from exc
    if poly.is_empty or len(poly.exterior.coords) < 4:
        raise GeometryError("polygon has too few points")
    if not poly.is_valid:
        fixed = make_valid(poly)
        if fixed.geom_type == "MultiPolygon":
            fixed = max(fixed.geoms, key=lambda g: g.area)
        if fixed.geom_type != "Polygon" or fixed.is_empty:
            raise GeometryError("polygon is self-intersecting")
        poly = fixed
    minx, miny, maxx, maxy = poly.bounds
    if not (-180 <= minx <= 180 and -180 <= maxx <= 180 and -90 <= miny <= 90 and -90 <= maxy <= 90):
        raise GeometryError("coordinates must be lon/lat in degrees (WGS84)")
    area = geodesic_area_ha(poly)
    if area <= 0.01:
        raise GeometryError("polygon area is too small")
    if area > MAX_AREA_HA:
        raise GeometryError(f"polygon is too large ({area:.0f} ha > {MAX_AREA_HA:.0f} ha)")
    c = poly.centroid
    return Field(polygon=poly, area_ha=area, centroid_lon=c.x, centroid_lat=c.y)
