import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { CompareRequest, Comparison, Lang } from "../../api/types";
import { variantName } from "./VariantCards";

export default function PdfPanel({ request, comparison, stressYearIndex }: { request: CompareRequest; comparison: Comparison; stressYearIndex: number | null }) {
  const { t, i18n } = useTranslation();
  const [farm, setFarm] = useState("");
  const [variant, setVariant] = useState(comparison.best_variant_id);
  const [lang, setLang] = useState<Lang>(i18n.language as Lang);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = async () => {
    setBusy(true);
    setError(null);
    try {
      const blob = await api.reportPdf({
        ...request,
        lang,
        farm_name: farm,
        selected_variant_id: variant,
        stress_year_index: stressYearIndex ?? undefined,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = { ru: "agro-sevooborot-plan.pdf", kk: "agro-auyspaly-egis-zhospary.pdf", en: "agro-rotation-plan.pdf" }[lang];
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card grid gap-4 md:grid-cols-4 md:items-end">
      <label className="block">
        <span className="label">{t("result.pdf.farm_name")}</span>
        <input className="input" value={farm} maxLength={120} onChange={(e) => setFarm(e.target.value)} />
      </label>
      <label className="block">
        <span className="label">{t("result.pdf.variant")}</span>
        <select className="input" value={variant} onChange={(e) => setVariant(e.target.value)}>
          {comparison.variants.map((v, i) => (
            <option key={v.id} value={v.id}>
              {i + 1}. {variantName(v, i18n.language as Lang, t)}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="label">{t("result.pdf.lang")}</span>
        <select className="input" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
          <option value="ru">{t("app.lang.ru_name")}</option>
          <option value="kk">{t("app.lang.kk_name")}</option>
          <option value="en">{t("app.lang.en_name")}</option>
        </select>
      </label>
      <button type="button" className="btn-primary" disabled={busy} onClick={() => void download()}>
        {busy ? t("result.pdf.preparing") : t("result.pdf.download")}
      </button>
      {error && <p className="text-sm text-status-bad md:col-span-4">{t("app.error")}: {error}</p>}
    </div>
  );
}
