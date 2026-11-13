import { expect, test } from 'vitest';
import { buildChartRows } from '@/lib/marketChart';

const market = [
  { order: 1, action_id: 'b', name: 'Бази даних' },
  { order: 2, action_id: 'a', name: 'API' },
  { order: 3, action_id: 'c', name: 'Тестування' },
];
const comps = [
  { action_id: 'a', action_name: 'API', score: 0.8, reason: 'r', evidence: [] },
  { action_id: 'c', action_name: 'Тестування', score: null, reason: '', evidence: [] },
  { action_id: 'z', action_name: 'Поза ринком', score: 0.9, reason: '', evidence: [] },
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
