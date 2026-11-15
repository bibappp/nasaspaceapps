import { Activity, CloudRain, Droplets, Flame, Leaf, Sigma, Thermometer } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Lang, Risk, RiskItem } from "../../api/types";
import { useCropName } from "../../lib/config";
import { fmtNum } from "../../lib/format";
import { KindBadge, LevelBadge } from "../ui/ui";

const ICONS: Record<string, typeof Leaf> = {
  precip_season: CloudRain,
  temperature_season: Thermometer,
  heat_days: Flame,
  vegetation: Leaf,
  soil_moisture: Droplets,
  drought_frequency: Sigma,
  model_drought_exposure: Activity,
};

/** Значение показателя риска одной строкой — с единицами и опорным значением. */
export function useRiskText() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const cropName = useCropName();
  return (i: RiskItem): { value: string; detail: string } => {
    const v = i.value ?? null;
    if (v === null) return { value: "—", detail: t("risk.no_data") };
    switch (i.id) {
      case "precip_season":
        return {
          value: `${fmtNum(v, 0)} ${t("units.mm")}`,
          detail: t("risk.detail.precip", { pct: i.reference ? fmtNum((v / i.reference) * 100, 0) : "—", ref: fmtNum(i.reference, 0), z: fmtNum(i.z, 2) }),
        };
      case "temperature_season":
        return {
          value: `${fmtNum(v, 1)} °C`,
          detail: t("risk.detail.temperature", { delta: i.reference != null ? `${v - i.reference > 0 ? "+" : ""}${fmtNum(v - i.reference, 1)}` : "—", ref: fmtNum(i.reference, 1), z: fmtNum(i.z, 2) }),
        };
      case "heat_days":
        return { value: t("risk.days", { count: v }), detail: t("risk.detail.heat", { threshold: fmtNum(i.threshold_c, 0), ref: fmtNum(i.reference, 1) }) };
      case "vegetation":
        return { value: `NDVI ${fmtNum(v, 2)}`, detail: t("risk.detail.vegetation", { ref: fmtNum(i.reference, 2), pct: fmtNum(i.percentile, 0) }) };
      case "soil_moisture":
        return i.fallback_for
          ? { value: `GWETROOT ${fmtNum(v, 2)}`, detail: t("risk.detail.moisture_fallback", { ratio: fmtNum(i.ratio, 2) }) }
          : { value: `${fmtNum(v, 3)} ${t("units.m3m3")}`, detail: t("risk.detail.moisture", { ratio: fmtNum(i.ratio, 2) }) };
      case "drought_frequency":
        return { value: `${fmtNum(v * 100, 0)} %`, detail: t("risk.detail.drought", { n: i.every_nth ?? "—", years: (i.dry_years ?? []).join(", ") }) };
      case "model_drought_exposure":
        return { value: `−${fmtNum(v, 1)} %`, detail: t("risk.detail.model", { crop: i.crop ? cropName(i.crop, lang) : "—", year: i.period ?? "" }) };
      default:
        return { value: `${fmtNum(v, 2)} ${i.unit ?? ""}`, detail: "" };
    }
  };
}

export function RiskCard({ item }: { item: RiskItem }) {
  const { t } = useTranslation();
  const text = useRiskText()(item);
  const Icon = ICONS[item.id] ?? Activity;
  return (
    <div className="panel flex flex-col p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium text-ink-2">
          <Icon className="h-4 w-4 text-ink-muted" />
          {t(`risk.item.${item.id}`)}
        </div>
        <LevelBadge level={item.level} />
      </div>
      <div className="mt-2 text-xl font-semibold tabular-nums text-ink">{text.value}</div>
      <p className="mt-1 flex-1 text-xs leading-relaxed text-ink-muted">{text.detail}</p>
      <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-line pt-2.5 text-xs text-ink-muted">
        <KindBadge kind={item.kind} />
        <span>{t(`sources.short.${item.source}`)}</span>
        {item.period && <span>· {item.period}</span>}
        {item.fallback_for && <span className="badge-amber">{t("risk.fallback")}</span>}
      </div>
    </div>
  );
}

export function RiskGrid({ risk, compact = false }: { risk: Risk; compact?: boolean }) {
  const items = compact ? risk.items.filter((i) => i.id !== "model_drought_exposure") : risk.items;
  return (
    <div className={`grid gap-3 sm:grid-cols-2 ${compact ? "xl:grid-cols-3" : "lg:grid-cols-3 xl:grid-cols-4"}`}>
      {items.map((i) => (
        <RiskCard key={i.id} item={i} />
      ))}
    </div>
  );
}
