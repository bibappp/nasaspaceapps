import { useCallback, useEffect, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { ApiError } from "../api/client";

/** Текст ошибки API для пользователя: известные коды бэкенда переводятся, остальное показывается как есть. */
export function errorText(e: unknown, t: TFunction): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return t("app.network_error");
    const key = `errors.${e.detail}`;
    const tr = t(key);
    if (tr !== key) return tr;
    if (e.status === 404) return t("errors.not_found");
    if (e.status === 503) return t("errors.source_unavailable", { detail: e.detail });
    return e.detail;
  }
  return e instanceof Error ? e.message : String(e);
}

export interface AsyncState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
  setData: (v: T) => void;
}

/** Загрузка данных с состояниями «загрузка / ошибка / готово»; устаревшие ответы отбрасываются. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [n, setN] = useState(0);
  const seq = useRef(0);
  useEffect(() => {
    const my = ++seq.current;
    setLoading(true);
    setError(null);
    fn()
      .then((v) => {
        if (my === seq.current) setData(v);
      })
      .catch((e: unknown) => {
        if (my === seq.current) setError(e);
      })
      .finally(() => {
        if (my === seq.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, n]);
  const reload = useCallback(() => setN((x) => x + 1), []);
  return { data, error, loading, reload, setData };
}

export function fmtDate(iso: string | null | undefined, lang: string): string {
  if (!iso) return "—";
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  const loc = lang === "kk" ? "kk-KZ" : lang === "en" ? "en-GB" : "ru-RU";
  return d.toLocaleDateString(loc, { day: "2-digit", month: "short", year: "numeric" });
}
