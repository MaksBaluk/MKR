import { bandFor, type Band } from '@/lib/bands';
import type { CompetencyResult, MarketSkill, SelfRatingValue } from '@/types';

/** One chart row. Deliberately has no market statistics: only the rank in market order and the name. */
export interface ChartRow {
  order: number;
  action_id: string;
  name: string;
  /** Candidate's assessed level on a 0–100 bar scale; null when the interview gave no assessment. */
  level: number | null;
  /** Candidate's own self-rating on the same scale; null when not given. */
  self: number | null;
  band: Band['label'] | null;
}

const pct = (v: number | null | undefined) => (v === null || v === undefined ? null : Math.round(v * 100));

export function buildChartRows(market: MarketSkill[], competencies: CompetencyResult[],
  selfRatings: SelfRatingValue[], limit?: number): ChartRow[] {
  const scores = new Map(competencies.map((c) => [c.action_id, c.score]));
  const selfs = new Map(selfRatings.map((r) => [r.action_id, r.value]));
  return market.slice(0, limit ?? market.length).map((m) => {
    const score = scores.get(m.action_id) ?? null;
    return {
      order: m.order,
      action_id: m.action_id,
      name: m.name,
      level: pct(score),
      self: pct(selfs.get(m.action_id)),
      band: score === null ? null : bandFor(score).label,
    };
  });
}
