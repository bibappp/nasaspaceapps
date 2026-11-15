"""Схемы запросов API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Lang = Literal["ru", "kk", "en"]


class HistoryItem(BaseModel):
    year: int = Field(ge=1990, le=2100)
    crop: str


class VariantIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    name: dict[str, str] | None = None
    crops: list[str] = Field(min_length=1, max_length=5)
    custom: bool = False


class FieldRequest(BaseModel):
    geometry: dict[str, Any]
    region: str
    history: list[HistoryItem] = Field(default_factory=list, max_length=10)
    priority: str = "max_income"
    horizon_years: int = Field(default=4, ge=3, le=5)

    @field_validator("history")
    @classmethod
    def unique_years(cls, v: list[HistoryItem]) -> list[HistoryItem]:
        years = [h.year for h in v]
        if len(set(years)) != len(years):
            raise ValueError("history contains duplicate years")
        return v

    def history_crops(self) -> list[str]:
        """Культуры по возрастанию года; последняя — предшественник первого года плана."""
        return [h.crop for h in sorted(self.history, key=lambda h: h.year)]


class CompareRequest(FieldRequest):
    variants: list[VariantIn] | None = Field(default=None, max_length=6)
    start_year: int | None = Field(default=None, ge=2000, le=2100)
    #: веса оценок {soil, water, income, risk}, заданные фермером; нормируются к сумме 1
    weights: dict[str, float] | None = None
    #: исторический засушливый год для стресс-теста (должен быть засушливым по данным поля)
    stress_year: int | None = Field(default=None, ge=1981, le=2100)


class ReportRequest(CompareRequest):
    lang: Lang = "ru"
    selected_variant_id: str | None = None
    farm_name: str = Field(default="", max_length=120)
    stress_year_index: int | None = Field(default=None, ge=1, le=5)


class RetroSubmission(BaseModel):
    farm_name: str = Field(min_length=1, max_length=120)
    contact: str = Field(min_length=3, max_length=160)
    region: str
    geometry: dict[str, Any] | None = None
    history: list[HistoryItem] = Field(min_length=2, max_length=30)
    evidence: str = Field(default="", max_length=2000)
    consent: bool


# ---------------------------------------------------------------- учётные записи и поля
class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    name: str = Field(default="", max_length=120)
    farm_name: str = Field(default="", max_length=160)
    lang: Lang = "ru"


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class ProfileIn(BaseModel):
    name: str = Field(default="", max_length=120)
    farm_name: str = Field(default="", max_length=160)
    lang: Lang = "ru"


class SoilInfo(BaseModel):
    """Сведения о почве, которые вносит фермер (например, из агрохимического обследования)."""

    humus_pct: float | None = Field(default=None, ge=0, le=20)
    ph: float | None = Field(default=None, ge=3, le=11)
    texture: Literal["sand", "sandy_loam", "loam", "clay_loam", "clay"] | None = None
    soil_type: str = Field(default="", max_length=120)
    survey_year: int | None = Field(default=None, ge=1950, le=2100)
    notes: str = Field(default="", max_length=1000)


class FieldIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    region: str
    geometry: dict[str, Any]
    history: list[HistoryItem] = Field(default_factory=list, max_length=10)
    history_is_scenario: bool = False
    soil: SoilInfo = Field(default_factory=SoilInfo)
    notes: str = Field(default="", max_length=4000)

    @field_validator("history")
    @classmethod
    def unique_years(cls, v: list[HistoryItem]) -> list[HistoryItem]:
        years = [h.year for h in v]
        if len(set(years)) != len(years):
            raise ValueError("history contains duplicate years")
        return sorted(v, key=lambda h: h.year)


class AnalysisIn(BaseModel):
    title: str = Field(default="", max_length=120)
    priority: str = "max_income"
    weights: dict[str, float] | None = None
    horizon_years: int = Field(default=4, ge=3, le=5)
    variants: list[VariantIn] | None = Field(default=None, max_length=6)
    start_year: int | None = Field(default=None, ge=2000, le=2100)
    stress_year: int | None = Field(default=None, ge=1981, le=2100)


# ---------------------------------------------------------------- ответ GET /api/fields/{id}/bare-soil
# Форма ответа зафиксирована в docs/contracts/bare_soil.example.json (согласована с фронтендом).
# Менять можно только добавлением необязательных полей.
class LocalizedText(BaseModel):
    ru: str
    kk: str
    en: str


class SourceMetaOut(BaseModel):
    """Источник данных — та же форма, что у ``monitoring.source_meta``."""

    id: str
    title: str
    resolution_m: float | None = None
    origin: str | None = None
    spatial_resolution: LocalizedText
    provenance: LocalizedText


class DataWarningOut(BaseModel):
    """Предупреждение о качестве данных — та же форма, что у ``DataWarning.as_dict``."""

    code: str
    source: str
    params: dict[str, Any] = Field(default_factory=dict)


class BareSoilJob(BaseModel):
    """Фоновая загрузка источника — как элементы ``jobs`` у /monitoring."""

    source: str
    status: str
    job: dict[str, Any] | None = None


class BareSoilPeriod(BaseModel):
    start_year: int
    end_year: int


class BareSoilHeadline(BaseModel):
    top_months: list[int] = Field(default_factory=list)
    max_median_exposure: float | None = None


class BareSoilDefinition(BaseModel):
    exposure: LocalizedText


class BareSoilThreshold(BaseModel):
    id: str
    value: float
    unit: str
    source: str
    status: str
    evidence: str
    note: str


class BareSoilMonth(BaseModel):
    month: int = Field(ge=1, le=12)
    state: Literal["ok", "snow", "missing"]
    bare_days: int | None = None
    erosive_wind_days: int | None = None
    dry_days: int | None = None
    joint_days: int | None = None
    days_in_month: int
    #: дни, когда известны все три условия (покров, ветер, сухость); exposure = joint_days / known_days
    known_days: int | None = None
    exposure: float | None = Field(default=None, ge=0, le=1)
    moisture_source: str | None = None
    quality: Literal["ok", "partial", "missing"]
    #: почему месяц не посчитан (только при state: missing): future | no_weather | ndvi_pending_fetch |
    #: ndvi_gap | ndvi_not_covered | no_moisture
    missing_reason: str | None = None


class BareSoilYear(BaseModel):
    year: int
    months: list[BareSoilMonth]


class BareSoilClimatology(BaseModel):
    month: int = Field(ge=1, le=12)
    exposure_median: float | None = None
    exposure_p90: float | None = None
    n_years: int


class CoverCropWindow(BaseModel):
    start: str  # "ММ-ДД"
    end: str
    basis: LocalizedText
    uncertainty: str
    #: языки, тексты которых требуют вычитки носителем (сейчас всегда ["kk"])
    needs_review: list[str] = Field(default_factory=list)


class CoverCropNote(BaseModel):
    """Почему окна покровной культуры нет (только при пустом cover_crop_windows)."""
    #: no_harvest_date | no_frost_data | no_risky_months | risk_before_harvest_only | frost_before_establishment
    reason: str
    basis: LocalizedText
    #: что делать вместо покровной культуры — общая рекомендация (advice_scope: general_guidance), не для поля
    advice: LocalizedText | None = None
    advice_scope: Literal["general_guidance"] | None = None
    #: источник рекомендации: {id, name, url, note}; note — как источник проверен
    advice_source: dict[str, str] | None = None
    needs_review: list[str] = Field(default_factory=list)


class BareSoilOut(BaseModel):
    field_id: int
    period: BareSoilPeriod
    #: ok — всё посчитано; partial — часть месяцев или фоновые загрузки ещё идут;
    #: loading — пока ничего не посчитано, загрузки идут; missing — посчитать нельзя (нет данных)
    status: Literal["ok", "partial", "loading", "missing"]
    jobs: list[BareSoilJob] = Field(default_factory=list)
    headline: BareSoilHeadline
    definition: BareSoilDefinition
    thresholds: list[BareSoilThreshold] = Field(default_factory=list)
    #: пороги, фактически применённые к полю (θ_wp из SoilGrids, порог GWETTOP по SMAP, даты заморозков)
    effective_thresholds: dict[str, Any] | None = None
    years: list[BareSoilYear]
    climatology: list[BareSoilClimatology] = Field(default_factory=list)
    cover_crop_windows: list[CoverCropWindow] = Field(default_factory=list)
    #: почему окон нет (null, если окна есть или расчёт не выполнялся)
    cover_crop_note: CoverCropNote | None = None
    sources: list[SourceMetaOut]
    warnings: list[DataWarningOut] = Field(default_factory=list)
