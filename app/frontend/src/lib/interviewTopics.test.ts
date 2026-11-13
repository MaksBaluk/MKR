import { expect, test } from 'vitest';
import type { TurnView } from '@/types';
import {
  INTERVIEW_PANEL_STRINGS, containsScoreLeak, deriveTopics,
} from '@/lib/interviewTopics';

const t = (id: string, action_id: string, answered: boolean): TurnView => ({
  id, sequence: 0, action_id, action_name: `Тема ${action_id}`, created_at: null,
  question_text: 'Q', question_source: 'llm', answer_text: answered ? 'a' : null, graded: false,
});

test('empty', () => expect(deriveTopics([])).toEqual([]));

test('first-seen order, answered vs current', () => {
  const r = deriveTopics([t('1', 'b', true), t('2', 'a', true), t('3', 'c', false)]);
  expect(r.map((x) => x.action_id)).toEqual(['b', 'a', 'c']);
  expect(r.map((x) => x.answeredCount)).toEqual([1, 1, 0]);
  expect(r.map((x) => x.isCurrent)).toEqual([false, false, true]);
});

test('repeated action counts once, answeredCount grows', () => {
  const r = deriveTopics([t('1', 'a', true), t('2', 'a', true), t('3', 'a', false)]);
  expect(r).toEqual([{ action_id: 'a', action_name: 'Тема a', answeredCount: 2, isCurrent: true }]);
});

test('leak detector', () => {
  for (const s of ['оцінено на 0.25', 'оцінено Django', 'оцінка: 4', 'рівень B2', 'Високий', 'Середній', 'Низький', '75 %', '80%'])
    expect(containsScoreLeak(s), s).toBe(true);
  expect(containsScoreLeak('2 з 10 тем')).toBe(false);
});

test('panel static strings never leak scores', () => {
  for (const s of INTERVIEW_PANEL_STRINGS) expect(containsScoreLeak(s), s).toBe(false);
});
