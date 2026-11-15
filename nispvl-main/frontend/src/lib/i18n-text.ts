import type { I18nText, Lang } from "../api/types";

export function tx(text: I18nText | null | undefined, lang: Lang): string {
  if (!text) return "";
  return text[lang] ?? text.ru ?? "";
}
