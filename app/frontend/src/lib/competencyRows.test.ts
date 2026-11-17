import { describe, expect, it } from 'vitest';
import { diffLabel, mergeCompetencyRows } from './competencyRows';

const actions = [{ id: 'a', label_uk: 'A' }, { id: 'b', label_uk: 'B' }, { id: 'c', label_uk: 'C' }];
const comp = (id: string, s: number | null, reason = '', sufficient = true) => ({
  action_id: id, action_name: id, score: s, interview_score: s, self_rating: null, reason, sufficient_evidence: sufficient,
  evidence: [],
});

describe('mergeCompetencyRows', () => {
  it('merges llm grade and self-rating by action id with diff in points', () => {
    const rows = mergeCompetencyRows(actions, [comp('a', 0.6)], { a: 0.8 });
    expect(rows[0]).toMatchObject({ id: 'a', name: 'A', llm: 0.6, self: 0.8, diff: 20 });
  });
  it('has no diff unless both values exist', () => {
    const rows = mergeCompetencyRows(actions, [comp('a', 0.6)], { b: 0.5 });
    expect(rows.find((r) => r.id === 'a')?.diff).toBeNull();
    expect(rows.find((r) => r.id === 'b')?.diff).toBeNull();
  });
  it('orders by importance for the direction, then keeps the original order', () => {
    const rows = mergeCompetencyRows(actions, [], {}, { b: 90, c: 90, a: 10 });
    expect(rows.map((r) => r.id)).toEqual(['b', 'c', 'a']);
  });
  it('actions without an importance value go last in the original order', () => {
    const rows = mergeCompetencyRows(actions, [], {}, { c: 50 });
    expect(rows.map((r) => r.id)).toEqual(['c', 'a', 'b']);
  });
  it('without importance data the original order is kept', () => {
    expect(mergeCompetencyRows(actions, [comp('c', 0.4)], {}).map((r) => r.id)).toEqual(['a', 'b', 'c']);
  });
  it('treats null scores as missing', () => {
    expect(mergeCompetencyRows(actions, [comp('a', null)], { a: null })[0]).toMatchObject({ llm: null, self: null });
  });
});

describe('reason and certainty', () => {
  it('carries the short reason and whether the evidence was sufficient', () => {
    const rows = mergeCompetencyRows(actions, [comp('a', 0.3, 'Відповідь загальна.', false)], {});
    expect(rows[0]).toMatchObject({ id: 'a', reason: 'Відповідь загальна.', sufficient: false });
    expect(rows.find((r) => r.id === 'b')).toMatchObject({ reason: null, sufficient: true });
  });
});

describe('diffLabel', () => {
  it('uses sign and words', () => {
    expect(diffLabel(15)).toBe('+15 в.п. — самооцінка вища');
    expect(diffLabel(-10)).toBe('−10 в.п. — самооцінка нижча');
    expect(diffLabel(0)).toBe('0 в.п. — оцінки збігаються');
  });
});
