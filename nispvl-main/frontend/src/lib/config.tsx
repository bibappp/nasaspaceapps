import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { AppConfig, CropInfo, Lang } from "../api/types";

interface ConfigState {
  config: AppConfig | null;
  error: string | null;
  reload: () => void;
}

const Ctx = createContext<ConfigState>({ config: null, error: null, reload: () => undefined });

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    let alive = true;
    setError(null);
    api
      .config()
      .then((c) => alive && setConfig(c))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [n]);
  return <Ctx.Provider value={{ config, error, reload: () => setN((x) => x + 1) }}>{children}</Ctx.Provider>;
}

export const useConfig = () => useContext(Ctx);

export function useCropName() {
  const { config } = useConfig();
  return (id: string, lang: Lang, short = true): string => {
    const c: CropInfo | undefined = config?.crops.find((x) => x.id === id);
    return c ? (short ? c.short : c.name)[lang] : id;
  };
}
