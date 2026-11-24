import type { DistributionRow } from '@/lib/marketChart';
import type { CompetencyResult } from '@/types';

export type Quadrant = 'strong_wanted' | 'wanted_gap' | 'strong_rare' | 'rare_gap';

export interface MatrixPoint {
  id: string;
  name: string;
  /** Share of the selected vacancies that need the skill, 0..100. */
  demand: number;
  /** Candidate's interview grade, 0..100. */
  score: number;
  quadrant: Quadrant;
}

export interface Matrix {
  points: MatrixPoint[];
  /** Skills of the market list the interview did not grade: they cannot be placed, and are not shown as zero. */
  ungraded: { id: string; name: string; demand: number }[];
  /** Demand cut: the median demand of the listed skills, so the split follows the data. */
  demandCut: number;
  /** Score cut: the «Високий» band of the results page. */
  scoreCut: number;
}

export const SCORE_CUT = 75;

const median = (xs: number[]): number => {
  if (xs.length === 0) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

export function quadrantOf(demand: number, score: number, demandCut: number, scoreCut = SCORE_CUT): Quadrant {
  const wanted = demand >= demandCut;
  const strong = score >= scoreCut;
  return wanted ? (strong ? 'strong_wanted' : 'wanted_gap') : (strong ? 'strong_rare' : 'rare_gap');
}

/** Market skills against the candidate's interview grades. Ungraded skills stay off the plot and are listed apart. */
export function buildMatrix(rows: DistributionRow[], competencies: CompetencyResult[]): Matrix {
  const grade = new Map(competencies.map((c) => [c.action_id, c.interview_score ?? c.score]));
  const demandCut = median(rows.map((r) => r.share));
  const points: MatrixPoint[] = [];
  const ungraded: Matrix['ungraded'] = [];
  for (const r of rows) {
    const g = grade.get(r.id);
    if (g === null || g === undefined) { ungraded.push({ id: r.id, name: r.name, demand: r.share }); continue; }
    const score = Math.round(Math.min(1, Math.max(0, g)) * 100);
    points.push({ id: r.id, name: r.name, demand: r.share, score, quadrant: quadrantOf(r.share, score, demandCut) });
  }
  return { points, ungraded, demandCut, scoreCut: SCORE_CUT };
}

export const QUADRANT_TEXT: Record<Quadrant, { title: string; hint: string }> = {
  strong_wanted: { title: 'Сильні й затребувані', hint: 'Ваша перевага на цьому ринку' },
  wanted_gap: { title: 'Затребувані, але є прогалина', hint: 'Найкращі кандидати для навчання' },
  strong_rare: { title: 'Сильні, але рідкісні', hint: 'Вмієте більше, ніж зазвичай просять' },
  rare_gap: { title: 'Менш затребувані', hint: 'Не пріоритет' },
};

/** Within a quadrant: the most demanded skills first. */
export function inQuadrant(m: Matrix, q: Quadrant): MatrixPoint[] {
  return m.points.filter((p) => p.quadrant === q).sort((a, b) => b.demand - a.demand || a.name.localeCompare(b.name, 'uk'));
}
