import i18n from "../i18n";

const NBSP = " ";

export function fmtInt(v: number): string {
  const s = Math.round(Math.abs(v)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return (v < 0 ? "−" : "") + s;
}

export function fmtNum(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const fixed = Math.abs(v).toFixed(digits);
  // десятичная запятая для ru/kk, точка для en
  const s = i18n.language === "en" ? fixed : fixed.replace(".", ",");
  return (v < 0 ? "−" : "") + s;
}

export function fmtSigned(v: number): string {
  return (v > 0 ? "+" : v < 0 ? "−" : "") + fmtInt(Math.abs(v));
}
