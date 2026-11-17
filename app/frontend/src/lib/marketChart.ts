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

export interface DistributionItem {
  action_id: string;
  name: string;
  share_percent: number;
  /** Vacancies of the track that need this action at a low, middle or high level (highest level per vacancy). */
  levels?: { low: number; mid: number; high: number };
}

export interface DistributionRow {
  id: string;
  name: string;
  /** Share of vacancies in the selected segment, 0..100. */
  share: number;
  levels?: { low: number; mid: number; high: number };
}

/** Per-track distribution rows: server order, at most fifteen, shares clamped to 0..100. No re-ranking here. */
export function distributionRows(items: DistributionItem[]): DistributionRow[] {
  return items.slice(0, 15).map((i) => ({
    id: i.action_id,
    name: i.name,
    share: Math.min(100, Math.max(0, i.share_percent)),
    ...(i.levels ? { levels: i.levels } : {}),
  }));
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

const TRACK_LABELS: Record<string, string> = { python: 'Python', marketing: 'Маркетинг', design: 'Дизайн' };

/** Market page shows only the candidate's own track; an unknown track falls back to python. */
export function trackOptions(profileTrack: string): { value: string; label: string }[] {
  const value = profileTrack in TRACK_LABELS ? profileTrack : 'python';
  return [{ value, label: TRACK_LABELS[value] }];
}

const LEVEL_LABELS = [
  { key: 'low', label: 'Низький' }, { key: 'mid', label: 'Середній' }, { key: 'high', label: 'Високий' },
] as const;

/** Required-level counts as whole-percent segments (they add up to 100 unless there are no vacancies). */
export function levelSegments(levels: { low: number; mid: number; high: number }) {
  const total = levels.low + levels.mid + levels.high;
  const rows = LEVEL_LABELS.map((l) => ({
    key: l.key, label: l.label, count: levels[l.key], percent: total === 0 ? 0 : Math.round((100 * levels[l.key]) / total),
  }));
  const diff = total === 0 ? 0 : 100 - rows.reduce((a, r) => a + r.percent, 0);
  if (diff !== 0) rows.reduce((big, r) => (r.count > big.count ? r : big)).percent += diff;
  return rows;
}
