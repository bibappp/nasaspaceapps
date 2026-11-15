import { useTranslation } from "react-i18next";
import type { Lang } from "../../api/types";

const LANGS: Lang[] = ["ru", "kk", "en"];

export default function LangSwitch({ dark = false }: { dark?: boolean }) {
  const { t, i18n } = useTranslation();
  return (
    <div role="group" aria-label={t("app.lang.switch")} className={`inline-flex rounded-md border p-0.5 ${dark ? "border-white/25" : "border-line-strong bg-white"}`}>
      {LANGS.map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => void i18n.changeLanguage(l)}
          aria-pressed={i18n.language === l}
          className={`h-7 rounded px-2 text-xs font-semibold ${
            i18n.language === l ? (dark ? "bg-white text-field-800" : "bg-field-700 text-white") : dark ? "text-white/80 hover:text-white" : "text-ink-muted hover:text-ink"
          }`}
        >
          {t(`app.lang.${l}`)}
        </button>
      ))}
    </div>
  );
}
