import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import kk from "./locales/kk.json";
import ru from "./locales/ru.json";
import type { Lang } from "./api/types";

const STORAGE_KEY = "agro.lang";
const LANGS: Lang[] = ["ru", "kk", "en"];

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && (LANGS as string[]).includes(saved)) return saved as Lang;
  } catch {
    /* хранилище недоступно */
  }
  return "ru";
}

void i18n.use(initReactI18next).init({
  resources: { ru: { translation: ru }, kk: { translation: kk }, en: { translation: en } },
  lng: initialLang(),
  fallbackLng: "ru",
  interpolation: { escapeValue: false },
  returnNull: false,
});

i18n.on("languageChanged", (lng) => {
  document.documentElement.lang = lng;
  try {
    localStorage.setItem(STORAGE_KEY, lng);
  } catch {
    /* ignore */
  }
});
document.documentElement.lang = i18n.language;

export default i18n;
