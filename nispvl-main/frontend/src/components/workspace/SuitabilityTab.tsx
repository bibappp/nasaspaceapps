import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { Lang } from "../../api/types";
import { errorText, useAsync } from "../../lib/async";
import { useCropName } from "../../lib/config";
import { fmtInt, fmtNum } from "../../lib/format";
import { ErrorBox, Loading, Notice, SectionTitle, Stat } from "../ui/ui";

const CAT: Record<string, string> = { favourable: "badge-green", conditional: "badge-amber", limited: "badge-red" };

export default function SuitabilityTab({ fieldId }: { fieldId: number }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const cropName = useCropName();
  const s = useAsync(() => api.fieldSuitability(fieldId), [fieldId]);
  if (s.error) return <ErrorBox message={errorText(s.error, t)} onRetry={s.reload} />;
  if (!s.data) return <Loading />;
  const { crops, context } = s.data;
  return (
    <div className="space-y-6">
      <Notice tone="warn">{t("suitability.scope")}</Notice>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label={t("suitability.water_normal")} value={`${fmtInt(context.water_normal_mm)} ${t("units.mm")}`} hint={t("suitability.water_hint")} />
        <Stat label={t("suitability.water_dry", { year: context.dry_year })} value={`${fmtInt(context.water_dry_mm)} ${t("units.mm")}`} />
        <Stat label={t("suitability.gdd")} value={context.gdd5_may_sep_mean === null ? "—" : fmtInt(context.gdd5_may_sep_mean)} hint={context.gdd_years ? t("suitability.gdd_hint", { from: context.gdd_years[0], to: context.gdd_years[1] }) : undefined} />
        <Stat label={t("suitability.predecessor")} value={context.predecessor ? cropName(context.predecessor, lang, false) : "—"} hint={context.soil ? t("result.summary.soil_detail", { humus: fmtNum(context.soil.humus_pct, 1), clay: fmtNum(context.soil.clay_pct, 0), sand: fmtNum(context.soil.sand_pct, 0), ph: fmtNum(context.soil.ph, 1) }) : undefined} />
      </div>
      <section>
        <SectionTitle title={t("suitability.title")} hint={t("suitability.hint")} />
        <div className="panel overflow-x-auto">
          <table className="table min-w-[960px]">
            <thead>
              <tr>
                <th>{t("suitability.crop")}</th>
                <th>{t("suitability.category")}</th>
                <th className="num">{t("suitability.need")}</th>
                <th className="num">{t("suitability.moisture_coef")}</th>
                <th className="num">{t("suitability.predecessor_effect")}</th>
                <th className="num">{t("suitability.drought_loss")}</th>
                <th className="num">{t("suitability.yield")}</th>
                <th className="num">{t("suitability.margin")}</th>
                <th>{t("suitability.flags")}</th>
                <th>{t("planner.confidence")}</th>
              </tr>
            </thead>
            <tbody>
              {crops.map((c) => (
                <tr key={c.crop}>
                  <td className="font-medium">{cropName(c.crop, lang, false)}<div className="text-xs font-normal text-ink-muted">{t(`groups.${c.group}`)}</div></td>
                  <td><span className={CAT[c.category]}>{t(`suitability.cat.${c.category}`)}</span></td>
                  <td className="num">{fmtInt(c.water_need_mm)}</td>
                  <td className="num">{fmtNum(c.moisture_coef, 2)}</td>
                  <td className="num">{c.predecessor_effect_pct > 0 ? "+" : ""}{fmtNum(c.predecessor_effect_pct, 0)} %</td>
                  <td className="num">−{fmtNum(c.drought_loss_pct, 0)} %</td>
                  <td className="num">{fmtNum(c.yield_t_ha, 2)}</td>
                  <td className={`num ${c.gross_margin_kzt_ha < 0 ? "text-status-bad" : ""}`}>{fmtInt(c.gross_margin_kzt_ha)}</td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {c.flags.length === 0 ? <span className="text-xs text-ink-muted">—</span> : c.flags.map((f) => <span key={f} className="badge-neutral">{t(`suitability.flag.${f}`)}</span>)}
                    </div>
                  </td>
                  <td className="text-xs">{t(`planner.conf.${c.confidence.level}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-ink-muted">{t("suitability.footnote")}</p>
      </section>
    </div>
  );
}
