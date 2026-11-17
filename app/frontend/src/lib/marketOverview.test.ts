import { describe, expect, test } from 'vitest';
import { compareRows, donutRows, kindRows, kindsShare, salaryRows } from '@/lib/marketOverview';

describe('donutRows', () => {
  test('orders by the given label order, adds percent and drops zeros', () => {
    const rows = donutRows({ SENIOR: 1, JUNIOR: 3, LEAD: 0 }, [
      { key: 'JUNIOR', label: 'Junior' }, { key: 'MIDDLE', label: 'Middle' },
      { key: 'SENIOR', label: 'Senior' }, { key: 'LEAD', label: 'Lead' },
    ]);
    expect(rows).toEqual([
      { key: 'JUNIOR', label: 'Junior', value: 3, percent: 75 },
      { key: 'SENIOR', label: 'Senior', value: 1, percent: 25 },
    ]);
  });
  test('empty input gives no rows', () => {
    expect(donutRows({}, [{ key: 'A', label: 'A' }])).toEqual([]);
  });
});

describe('salaryRows', () => {
  test('marks levels with fewer than three priced vacancies as not enough data', () => {
    const rows = salaryRows([
      { seniority: 'JUNIOR', count: 2, min: 1000, avg: 1500, max: 2000, currency: 'USD' },
      { seniority: 'SENIOR', count: 5, min: 3000, avg: 4000, max: 5000, currency: 'USD' },
    ]);
    expect(rows.map((r) => [r.label, r.enough, r.range])).toEqual([['Junior', false, 1000], ['Senior', true, 2000]]);
  });
});

describe('salaryRows order', () => {
  test('levels follow career order, not the alphabet', () => {
    const mk = (seniority: string) => ({ seniority, count: 5, min: 1, avg: 2, max: 3, currency: 'USD' });
    expect(salaryRows([mk('LEAD'), mk('JUNIOR'), mk('SENIOR'), mk('MIDDLE')]).map((r) => r.key))
      .toEqual(['JUNIOR', 'MIDDLE', 'SENIOR', 'LEAD']);
  });
});

describe('kindsShare', () => {
  test('mandatory and desired shares sum to 100', () => {
    const s = kindsShare([
      { action_id: 'a', name: 'A', mandatory: 6, desired: 2, avg_required_level: 2 },
      { action_id: 'b', name: 'B', mandatory: 0, desired: 2, avg_required_level: 2 },
    ]);
    expect(s).toEqual({ mandatory: 60, desired: 40 });
  });
  test('no requirements gives zeros', () => {
    expect(kindsShare([])).toEqual({ mandatory: 0, desired: 0 });
  });
});

describe('compareRows', () => {
  const kinds = [
    { action_id: 'a', name: 'A', mandatory: 8, desired: 1, avg_required_level: 2.5 },
    { action_id: 'b', name: 'B', mandatory: 2, desired: 0, avg_required_level: 1.5 },
    { action_id: 'c', name: 'C', mandatory: 1, desired: 0, avg_required_level: 3 },
  ];
  const graded = (id: string, s: number | null) => ({ action_id: id, action_name: id, interview_score: s });
  test('keeps every top skill: market = average required level as a percent of the top level, candidate null if ungraded', () => {
    expect(compareRows(kinds, [graded('a', 0.8), graded('b', null)], 8)).toEqual([
      { id: 'a', name: 'A', market: 83, candidate: 80 },
      { id: 'b', name: 'B', market: 50, candidate: null },
      { id: 'c', name: 'C', market: 100, candidate: null },
    ]);
  });
  test('respects the top limit in demand order', () => {
    expect(compareRows(kinds, [], 2).map((r) => r.id)).toEqual(['a', 'b']);
  });
  test('empty input gives no rows', () => {
    expect(compareRows([], [])).toEqual([]);
  });
});

describe('kindRows', () => {
  test('keeps the demand order, limits the rows and sums both kinds', () => {
    const kinds = [
      { action_id: 'a', name: 'A', mandatory: 6, desired: 2, avg_required_level: 2 },
      { action_id: 'b', name: 'B', mandatory: 1, desired: 3, avg_required_level: 2 },
      { action_id: 'c', name: 'C', mandatory: 0, desired: 1, avg_required_level: 2 },
    ];
    expect(kindRows(kinds, 2)).toEqual([
      { id: 'a', name: 'A', mandatory: 6, desired: 2, total: 8 },
      { id: 'b', name: 'B', mandatory: 1, desired: 3, total: 4 },
    ]);
  });
  test('empty input gives no rows', () => {
    expect(kindRows([])).toEqual([]);
  });
});
