import { useTranslation } from "react-i18next";
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Comparison, Lang } from "../../api/types";
import { useCropName } from "../../lib/config";
import { fmtInt, fmtNum } from "../../lib/format";
import { variantName } from "./VariantCards";

export default function StressTest({
  comparison,
  yearIndex,
  onYearIndex,
}: {
  comparison: Comparison;
  yearIndex: number | null;
  onYearIndex: (i: number | null) => void;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const cropName = useCropName();
  const dryYear = comparison.conditions.dry_year;
  const first = comparison.variants[0];

  const rows = comparison.variants.map((v, i) => {
    const idx = yearIndex ?? v.stress.worst_year_index;
    const py = v.stress.per_year[idx - 1];
    return {
      key: v.id,
      label: "ABCDEF"[i] ?? `${i + 1}`,
      name: variantName(v, lang, t),
      normal: v.stress.total_normal_kzt_ha / 1000,
      dry: (py?.total_if_dry_kzt_ha ?? 0) / 1000,
      loss: py?.loss_kzt_ha ?? 0,
      year: py?.year,
      crop: py ? cropName(py.crop, lang) : "",
    };
  });

  return (
    <div className="space-y-4">
      <p>{t("result.stress.intro", { year: dryYear })}</p>
      <label className="block max-w-sm">
        <span className="label">{t("result.stress.which_year")}</span>
        <select
          className="input"
          value={yearIndex ?? ""}
          onChange={(e) => onYearIndex(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">{t("result.stress.worst")}</option>
          {first?.years.map((y) => (
            <option key={y.index} value={y.index}>
              {y.year} ({t("result.compare.chain_year", { n: y.index })})
            </option>
          ))}
        </select>
      </label>
      <figure className="card">
        <figcaption className="h3 mb-2">{t("result.stress.chart")}</figcaption>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }} barGap={2}>
              <CartesianGrid stroke="#E3E6EA" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} width={52} />
              <ReferenceLine y={0} stroke="#8a8a8a" />
              <Tooltip
                labelFormatter={(_, p) => (p?.[0]?.payload as { name?: string } | undefined)?.name ?? ""}
                formatter={(v: number, k: string) => [fmtNum(v, 1), k === "normal" ? t("result.stress.normal") : t("result.stress.dry")]}
              />
              <Legend formatter={(k: string) => (k === "normal" ? t("result.stress.normal") : t("result.stress.dry"))} wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="normal" fill="#2a78d6" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="dry" fill="#eb6834" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </figure>
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-surface">
            <tr>
              <th className="px-3 py-2 text-left">{t("result.forecast.table_variant")}</th>
              <th className="px-3 py-2 text-right">{t("result.stress.normal")}</th>
              <th className="px-3 py-2 text-right">{t("result.stress.dry")}</th>
              <th className="px-3 py-2 text-right">{t("result.stress.loss")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t">
                <td className="px-3 py-2">
                  <b>{r.label}.</b> {r.name}
                  <div className="text-xs text-ink-muted">{r.year} · {r.crop}</div>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{fmtInt(r.normal * 1000)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmtInt(r.dry * 1000)}</td>
                <td className="px-3 py-2 text-right font-semibold tabular-nums text-red-800">−{fmtInt(r.loss)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
