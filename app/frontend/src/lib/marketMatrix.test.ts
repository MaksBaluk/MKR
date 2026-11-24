import { describe, expect, test } from 'vitest';
import { buildMatrix, inQuadrant, quadrantOf } from '@/lib/marketMatrix';
import type { DistributionRow } from '@/lib/marketChart';
import type { CompetencyResult } from '@/types';

const row = (id: string, share: number): DistributionRow => ({ id, name: id.toUpperCase(), share });
const comp = (id: string, s: number | null): CompetencyResult => ({
  action_id: id, action_name: id, score: s, interview_score: s, self_rating: null, reason: '', sufficient_evidence: true, evidence: [],
});

describe('marketMatrix', () => {
  test('quadrants split on demand cut and the 75 score cut', () => {
    expect(quadrantOf(60, 80, 50)).toBe('strong_wanted');
    expect(quadrantOf(60, 74, 50)).toBe('wanted_gap');
    expect(quadrantOf(40, 75, 50)).toBe('strong_rare');
    expect(quadrantOf(40, 10, 50)).toBe('rare_gap');
    expect(quadrantOf(50, 75, 50)).toBe('strong_wanted');
  });
  test('demand cut is the median of listed skills; ungraded skills are not plotted as zero', () => {
    const m = buildMatrix([row('a', 80), row('b', 60), row('c', 40), row('d', 20)], [comp('a', 0.9), comp('b', 0.4), comp('c', null)]);
    expect(m.demandCut).toBe(50);
    expect(m.points.map((p) => [p.id, p.score, p.quadrant])).toEqual([['a', 90, 'strong_wanted'], ['b', 40, 'wanted_gap']]);
    expect(m.ungraded.map((u) => u.id)).toEqual(['c', 'd']);
  });
  test('empty input is safe', () => {
    const m = buildMatrix([], []);
    expect(m.points).toEqual([]);
    expect(m.demandCut).toBe(0);
  });
  test('quadrant list is ordered by demand', () => {
    const m = buildMatrix([row('a', 70), row('b', 90), row('c', 10)], [comp('a', 0.2), comp('b', 0.1), comp('c', 0.9)]);
    expect(inQuadrant(m, 'wanted_gap').map((p) => p.id)).toEqual(['b', 'a']);
  });
});
