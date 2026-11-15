"""ISRIC SoilGrids 2.0 REST: органический углерод, глина, песок, pH по слоям до 1 м.

Сервис: https://rest.isric.org/soilgrids/v2.0/properties/query (бета, бывает недоступен).
Запрос делается в точке центроида поля. Значения приводятся к обычным единицам
делением на ``d_factor`` из ответа API.
"""
from __future__ import annotations

from datetime import date

from ..geometry import Field
from .base import DataSource, DataWarning, ProgressCallback, SourceError, http_client

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPERTIES = ["soc", "clay", "sand", "phh2o"]
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm"]


class SoilGridsSource(DataSource):
    id = "soilgrids"

    def cache_parts(self, field: Field, start: date, end: date) -> dict:
        # карта статична: период в ключ не входит; точка округлена до ~100 м
        return {"lat": round(field.centroid_lat, 3), "lon": round(field.centroid_lon, 3)}

    async def _fetch_live(
        self, field: Field, start: date, end: date, progress: ProgressCallback | None = None
    ) -> dict:
        params: list[tuple[str, str]] = [
            ("lon", f"{field.centroid_lon:.5f}"),
            ("lat", f"{field.centroid_lat:.5f}"),
        ]
        params += [("property", p) for p in PROPERTIES]
        params += [("depth", d) for d in DEPTHS]
        params += [("value", "mean"), ("value", "Q0.05"), ("value", "Q0.95")]
        async with http_client(timeout=45.0) as client:
            resp = await client.get(URL, params=params)
        if resp.status_code != 200:
            raise SourceError(f"SoilGrids HTTP {resp.status_code}: {resp.text[:200]}")
        layers = resp.json().get("properties", {}).get("layers", [])
        if not layers:
            raise SourceError("SoilGrids: no layers in response")
        out: dict[str, dict] = {}
        for layer in layers:
            name = layer["name"]
            d_factor = layer["unit_measure"]["d_factor"] or 1
            depths = {}
            for d in layer["depths"]:
                mean = d["values"].get("mean")
                depths[d["label"]] = {
                    "mean": None if mean is None else mean / d_factor,
                    # 90 %-й интервал предсказания модели SoilGrids
                    "q05": None if d["values"].get("Q0.05") is None else d["values"]["Q0.05"] / d_factor,
                    "q95": None if d["values"].get("Q0.95") is None else d["values"]["Q0.95"] / d_factor,
                    "top_cm": d["range"]["top_depth"],
                    "bottom_cm": d["range"]["bottom_depth"],
                }
            out[name] = {"unit": layer["unit_measure"]["target_units"], "depths": depths}
        if all(v["depths"].get("0-5cm", {}).get("mean") is None for v in out.values()):
            raise SourceError("SoilGrids: no data at this point (water, urban area or outside coverage)")
        return {"lat": field.centroid_lat, "lon": field.centroid_lon, "properties": out}

    def _fallback(self, field: Field) -> tuple[dict, DataWarning] | None:
        demo = self.read_demo()
        if demo is None:
            return None
        return demo, DataWarning("soil_fallback_demo", self.id)
