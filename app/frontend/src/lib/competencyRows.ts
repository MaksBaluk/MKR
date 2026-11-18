import type { CompetencyResult } from '@/types';

export interface CompetencyRow {
  id: string;
  name: string;
  /** Interview grade of the LLM, 0..1, read-only. */
  llm: number | null;
  /** Candidate's own rating, 0..1. */
  self: number | null;
  /** self minus llm in percentage points (integer), only when both exist. */
  diff: number | null;
  /** Short explanation of the interview grade, null when there is none. */
  reason: string | null;
  /** False when the grade rests on thin evidence (shown as rough). */
  sufficient: boolean;
}

/** One row per action of the track, most important for the direction first (market demand), then the original order. */
export function mergeCompetencyRows(
  actions: { id: string; label_uk: string }[],
  competencies: CompetencyResult[],
  ratings: Record<string, number | null>,
  importance: Record<string, number> = {},
): CompetencyRow[] {
  const llm = new Map(competencies.map((c) => [c.action_id, c.interview_score]));
  const detail = new Map(competencies.map((c) => [c.action_id, c]));
  const rows = actions.map((a): CompetencyRow => {
    const l = llm.get(a.id) ?? null;
    const s = ratings[a.id] ?? null;
    const d = detail.get(a.id);
    return {
      id: a.id, name: a.label_uk, llm: l, self: s, diff: l !== null && s !== null ? Math.round((s - l) * 100) : null,
      reason: d?.reason ? d.reason : null, sufficient: d ? d.sufficient_evidence : true,
    };
  });
  return rows.map((r, i) => ({ r, i }))
    .sort((x, y) => (importance[y.r.id] ?? -1) - (importance[x.r.id] ?? -1) || x.i - y.i)
    .map((x) => x.r);
}

export function diffLabel(diff: number): string {
  if (diff === 0) return 'оцінки збігаються';
  return diff > 0 ? `самооцінка вища на ${diff}%` : `самооцінка нижча на ${Math.abs(diff)}%`;
}
