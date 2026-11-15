import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Comparison, Lang } from "../../api/types";
import { seriesColor } from "../../lib/colors";
import { useCropName } from "../../lib/config";
import { fmtInt, fmtNum } from "../../lib/format";
import { variantName } from "./VariantCards";

const AXIS = { fontSize: 12, fill: "#5B6470" };

function Chart({ comparison, metric, title }: { comparison: Comparison; metric: "income" | "soil"; title: string }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const cropName = useCropName();
  const rows = comparison.variants[0]?.years.map((_, i) => {
    const row: Record<string, number | string> = { year: comparison.variants[0]?.years[i]?.year ?? i };
    comparison.variants.forEach((v) => {
      const y = v.years[i];
      if (y) {
        row[v.id] = metric === "income" ? y.income_kzt_ha / 1000 : y.soil_index;
        row[`${v.id}_crop`] = cropName(y.crop, lang);
      }
    });
    return row;
  }) ?? [];
  return (
    <figure className="card">
      <figcaption className="h3 mb-2">{title}</figcaption>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#E3E6EA" vertical={false} />
            <XAxis dataKey="year" tick={AXIS} />
            <YAxis tick={AXIS} width={52} domain={metric === "soil" ? ["auto", "auto"] : undefined} />
            {metric === "income" && <ReferenceLine y={0} stroke="#8a8a8a" />}
            {metric === "soil" && <ReferenceLine y={100} stroke="#8a8a8a" strokeDasharray="4 4" />}
            <Tooltip
              formatter={(value: number, key: string, item) => {
                const v = comparison.variants.find((x) => x.id === key);
                const crop = (item.payload as Record<string, string>)[`${key}_crop`];
                return [metric === "income" ? `${fmtNum(value, 1)} (${crop})` : `${fmtNum(value, 1)} (${crop})`, v ? variantName(v, lang, t) : key];
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} formatter={(key: string) => {
              const v = comparison.variants.find((x) => x.id === key);
              return v ? variantName(v, lang, t) : key;
            }} />
            {comparison.variants.map((v, i) => (
              <Line key={v.id} dataKey={v.id} stroke={seriesColor(i)} strokeWidth={2.5} dot={{ r: 5, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 7 }} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

export default function ForecastCharts({ comparison }: { comparison: Comparison }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const cropName = useCropName();
  const [table, setTable] = useState(false);
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Chart comparison={comparison} metric="income" title={t("result.forecast.income")} />
        <Chart comparison={comparison} metric="soil" title={t("result.forecast.soil")} />
      </div>
      <p className="muted">{t("result.forecast.note")}</p>
      <button type="button" className="btn-ghost px-0" onClick={() => setTable((x) => !x)} aria-expanded={table}>
        {table ? t("result.compare.hide_table") : t("result.compare.show_table")}
      </button>
      {table && (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="bg-surface">
              <tr>
                <th className="px-3 py-2 text-left">{t("result.forecast.table_variant")}</th>
                {comparison.variants[0]?.years.map((y) => (
                  <th key={y.year} className="px-3 py-2 text-right">{y.year}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {comparison.variants.map((v) => (
                <tr key={v.id} className="border-t align-top">
                  <td className="px-3 py-2 font-semibold">{variantName(v, lang, t)}</td>
                  {v.years.map((y) => (
                    <td key={y.year} className="px-3 py-2 text-right tabular-nums">
                      <div className="text-xs text-ink-muted">{cropName(y.crop, lang)}</div>
                      <div>{fmtInt(y.income_kzt_ha)} {t("result.compare.per_ha")}</div>
                      <div className="text-xs">{fmtNum(y.yield_t_ha, 2)} {t("units.t_ha")} · {t("result.scores.soil")} {fmtNum(y.soil_index, 1)}</div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
