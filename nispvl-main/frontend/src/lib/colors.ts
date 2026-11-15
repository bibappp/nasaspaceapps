// Категориальная палитра вариантов: фиксированный порядок, цвет закреплён за вариантом,
// а не за местом в рейтинге. Проверена валидатором (CVD и обычное зрение).
// Три цвета ниже 3:1 к фону — поэтому у графиков всегда есть легенда с подписями и таблица.
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"];

export function seriesColor(index: number): string {
  return SERIES[index % SERIES.length] ?? "#2a78d6";
}

type Stop = [number, string];

function lerp(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return "#" + pa.map((v, i) => Math.round(v + ((pb[i] ?? v) - v) * t).toString(16).padStart(2, "0")).join("");
}

function ramp(stops: Stop[]) {
  return (t: number): string => {
    const x = Math.min(1, Math.max(0, t));
    for (let i = 1; i < stops.length; i++) {
      const [t0, c0] = stops[i - 1] as Stop;
      const [t1, c1] = stops[i] as Stop;
      if (x <= t1) return lerp(c0, c1, (x - t0) / (t1 - t0));
    }
    return (stops[stops.length - 1] as Stop)[1];
  };
}

// Последовательные шкалы — один тон от светлого к тёмному.
export const RAMPS: Record<string, (t: number) => string> = {
  ndvi: ramp([[0, "#f3efe0"], [0.5, "#9cc27a"], [1, "#1f5d14"]]),
  soil_moisture: ramp([[0, "#eef4fb"], [0.5, "#7fb0e0"], [1, "#1c4f8f"]]),
  precip: ramp([[0, "#eef4fb"], [0.5, "#7fb0e0"], [1, "#1c4f8f"]]),
  // Экспозиция голой почвы: светлый песок → тёмная охра. В ячейке всегда есть число.
  exposure: ramp([[0, "#F8F5F0"], [0.5, "#CDB48F"], [1, "#5F4728"]]),
};
