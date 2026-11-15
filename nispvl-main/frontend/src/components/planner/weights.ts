import type { Comparison, ScoreKey, ScoreWeights, VariantResult } from "../../api/types";

export const SCORE_KEYS: ScoreKey[] = ["soil", "water", "income", "risk"];

export function normalize(w: ScoreWeights): ScoreWeights {
  const total = SCORE_KEYS.reduce((s, k) => s + Math.max(0, w[k]), 0);
  if (total <= 0) return { soil: 0.25, water: 0.25, income: 0.25, risk: 0.25 };
  return Object.fromEntries(SCORE_KEYS.map((k) => [k, Math.max(0, w[k]) / total])) as ScoreWeights;
}

export function sameWeights(a: ScoreWeights, b: ScoreWeights): boolean {
  const na = normalize(a), nb = normalize(b);
  return SCORE_KEYS.every((k) => Math.abs(na[k] - nb[k]) < 0.005);
}

export interface Ranked {
  v: VariantResult;
  index: number;
  weighted: number;
  rank: number;
  contributions: Record<ScoreKey, number>;
}

/**
 * Перерасчёт рейтинга под новые веса без запроса к серверу. Оценки 1–5 не зависят от весов
 * (они нормируются по сравниваемым вариантам), поэтому взвешенный балл = Σ wₖ·scoreₖ —
 * та же формула, что в backend/app/model/rotation.py.
 */
export function rank(comparison: Comparison, weights: ScoreWeights): Ranked[] {
  const w = normalize(weights);
  // при сохранённых весах берём балл сервера как есть — без расхождений округления
  const saved = sameWeights(weights, comparisonWeights(comparison));
  const rows = comparison.variants.map((v, index) => {
    const contributions = Object.fromEntries(SCORE_KEYS.map((k) => [k, w[k] * v.scores[k].score])) as Record<ScoreKey, number>;
    const weighted = saved ? v.weighted_score : Math.round(SCORE_KEYS.reduce((s, k) => s + contributions[k], 0) * 100) / 100;
    return { v, index, weighted, rank: 0, contributions };
  });
  const sorted = [...rows].sort((a, b) => b.weighted - a.weighted);
  sorted.forEach((r, i) => (r.rank = i + 1));
  return rows;
}

export function comparisonWeights(c: Comparison): ScoreWeights {
  return { soil: c.weights.soil, water: c.weights.water, income: c.weights.income, risk: c.weights.risk };
}
