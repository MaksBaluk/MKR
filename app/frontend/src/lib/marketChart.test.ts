import { describe, expect, test } from 'vitest';
import { buildChartRows, distributionRows, trackOptions } from '@/lib/marketChart';

const market = [
  { order: 1, action_id: 'b', name: 'Бази даних' },
  { order: 2, action_id: 'a', name: 'API' },
  { order: 3, action_id: 'c', name: 'Тестування' },
];
const comps = [
  { action_id: 'a', action_name: 'API', score: 0.8, interview_score: 0.8, self_rating: null, reason: 'r', sufficient_evidence: true, evidence: [] },
  { action_id: 'c', action_name: 'Тестування', score: null, interview_score: null, self_rating: null, reason: '', sufficient_evidence: true, evidence: [] },
  { action_id: 'z', action_name: 'Поза ринком', score: 0.9, interview_score: 0.9, self_rating: null, reason: '', sufficient_evidence: true, evidence: [] },
];

test('keeps market order, merges assessed level and self-rating', () => {
  const rows = buildChartRows(market, comps, [{ action_id: 'b', value: 0.45 }, { action_id: 'a', value: null }]);
  expect(rows.map((r) => r.action_id)).toEqual(['b', 'a', 'c']);
  expect(rows.map((r) => r.order)).toEqual([1, 2, 3]);
  expect(rows[0]).toMatchObject({ level: null, self: 45, band: null });
  expect(rows[1]).toMatchObject({ level: 80, self: null, band: 'Високий' });
  expect(rows[2]).toMatchObject({ level: null, self: null });
});

test('limit trims to the top of the market order', () => {
  expect(buildChartRows(market, comps, [], 2).map((r) => r.action_id)).toEqual(['b', 'a']);
});

test('output carries no market statistics', () => {
  const [row] = buildChartRows(market, comps, []);
  expect(Object.keys(row).sort()).toEqual(['action_id', 'band', 'level', 'name', 'order', 'self']);
});

describe('distributionRows', () => {
  test('keeps server order and clamps shares to 0..100', () => {
    expect(distributionRows([
      { action_id: 'x', name: 'X', share_percent: 120 },
      { action_id: 'y', name: 'Y', share_percent: -5 },
      { action_id: 'z', name: 'Z', share_percent: 40 },
    ])).toEqual([
      { id: 'x', name: 'X', share: 100 },
      { id: 'y', name: 'Y', share: 0 },
      { id: 'z', name: 'Z', share: 40 },
    ]);
  });

  test('shows at most fifteen rows', () => {
    const many = Array.from({ length: 20 }, (_, i) => ({ action_id: `a${i}`, name: `n${i}`, share_percent: 50 }));
    expect(distributionRows(many)).toHaveLength(15);
  });

  test('empty input gives no rows', () => {
    expect(distributionRows([])).toEqual([]);
  });
});

describe('trackOptions', () => {
  test('market shows only the candidate track', () => {
    expect(trackOptions('marketing')).toEqual([{ value: 'marketing', label: 'Маркетинг' }]);
    expect(trackOptions('python')).toEqual([{ value: 'python', label: 'Python' }]);
  });

  test('unknown track falls back to python', () => {
    expect(trackOptions('devops')).toEqual([{ value: 'python', label: 'Python' }]);
  });
});

describe('levelSegments', () => {
  test('turns required-level counts into whole-percent segments that add up to 100', async () => {
    const { levelSegments } = await import('@/lib/marketChart');
    expect(levelSegments({ low: 11, mid: 29, high: 7 })).toEqual([
      { key: 'low', label: 'Низький', count: 11, percent: 23 },
      { key: 'mid', label: 'Середній', count: 29, percent: 62 },
      { key: 'high', label: 'Високий', count: 7, percent: 15 },
    ]);
  });
  test('no vacancies gives zero percent everywhere', async () => {
    const { levelSegments } = await import('@/lib/marketChart');
    expect(levelSegments({ low: 0, mid: 0, high: 0 }).map((s) => s.percent)).toEqual([0, 0, 0]);
  });
});
