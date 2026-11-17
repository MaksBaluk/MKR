/** Pure data shaping for the market page charts. Numbers come from the API; nothing is ranked here. */

export interface KindsItem { action_id: string; name: string; mandatory: number; desired: number; avg_required_level: number }
export interface SalaryItem { seniority: string; count: number; min: number; avg: number; max: number; currency: string }
export interface MarketOverview {
  track: string;
  vacancies_total: number;
  seniority: Record<string, number>;
  work_mode: Record<string, number>;
  salary: SalaryItem[];
  requirement_kinds: KindsItem[];
}

export const SENIORITY_LABELS = [
  { key: 'JUNIOR', label: 'Junior' }, { key: 'MIDDLE', label: 'Middle' },
  { key: 'SENIOR', label: 'Senior' }, { key: 'LEAD', label: 'Lead' },
];
export const WORK_MODE_LABELS = [
  { key: 'OFFICE', label: 'Офіс' }, { key: 'HYBRID', label: 'Гібрид' }, { key: 'REMOTE', label: 'Віддалено' },
];

export function donutRows(counts: Record<string, number>, order: { key: string; label: string }[]) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  return order
    .filter((o) => (counts[o.key] ?? 0) > 0)
    .map((o) => ({ key: o.key, label: o.label, value: counts[o.key], percent: Math.round((100 * counts[o.key]) / total) }));
}

const MIN_PRICED = 3;

/** Floating-bar rows: `base` is the minimum, `range` the span up to the maximum; thin levels are marked, not drawn. */
export function salaryRows(salary: SalaryItem[]) {
  const order = (k: string) => SENIORITY_LABELS.findIndex((l) => l.key === k);
  return [...salary].sort((a, b) => order(a.seniority) - order(b.seniority)).map((s) => ({
    key: s.seniority,
    label: SENIORITY_LABELS.find((l) => l.key === s.seniority)?.label ?? s.seniority,
    count: s.count, min: s.min, avg: s.avg, max: s.max, currency: s.currency,
    base: s.min, range: s.max - s.min, enough: s.count >= MIN_PRICED,
  }));
}

/** Share of mandatory versus desired requirement mentions, whole percents that add up to 100. */
export function kindsShare(kinds: KindsItem[]): { mandatory: number; desired: number } {
  const mandatory = kinds.reduce((a, k) => a + k.mandatory, 0);
  const desired = kinds.reduce((a, k) => a + k.desired, 0);
  const total = mandatory + desired;
  if (total === 0) return { mandatory: 0, desired: 0 };
  const m = Math.round((100 * mandatory) / total);
  return { mandatory: m, desired: 100 - m };
}

/**
 * Rows for «your level against the market»: the top skills by demand. Market = the average level vacancies require
 * (1..3) as a percent of the top level; candidate = the interview grade, null when the skill was not graded.
 */
export function compareRows(
  kinds: KindsItem[], competencies: { action_id: string; action_name: string; interview_score: number | null }[], top = 8,
) {
  const grade = new Map(competencies.map((c) => [c.action_id, c.interview_score]));
  return kinds.slice(0, top).map((k) => {
    const score = grade.get(k.action_id);
    return {
      id: k.action_id, name: k.name,
      market: Math.min(100, Math.round((100 * k.avg_required_level) / 3)),
      candidate: score === null || score === undefined ? null : Math.round(score * 100),
    };
  });
}

/** Per-competency rows for the mandatory-vs-desired chart: demand order from the API, limited, counts of vacancies. */
export function kindRows(kinds: KindsItem[], top = 8) {
  return kinds.slice(0, top).map((k) => ({
    id: k.action_id, name: k.name, mandatory: k.mandatory, desired: k.desired, total: k.mandatory + k.desired,
  }));
}
