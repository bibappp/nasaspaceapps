import type { TFunction } from "i18next";
import type { VariantResult } from "../../api/types";
import { fmtNum } from "../../lib/format";

/** One-line bare-soil summary for rotation explanations when the API provides metrics. */
export function bareSoilLine(v: VariantResult, t: TFunction): string | null {
  const bare = (
    v as VariantResult & {
      bare_soil?: { bare_days_per_year?: number | null; mean_exposure?: number | null };
    }
  ).bare_soil;
  if (!bare || bare.bare_days_per_year == null || bare.mean_exposure == null) return null;
  return t("planner.bare_soil_line", {
    days: Math.round(bare.bare_days_per_year),
    exposure: fmtNum(bare.mean_exposure, 2),
  });
}