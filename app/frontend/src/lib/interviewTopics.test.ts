import { expect, test } from 'vitest';
import type { TurnView } from '@/types';
import {
  PANEL_TEXT, allPanelStrings, containsScoreLeak, deriveTopics, topicsCountLabel,
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

test('same action_name, different action_id stay separate', () => {
  const x = { ...t('2', 'b', false), action_name: 'Тема a' };
  expect(deriveTopics([t('1', 'a', true), x])).toHaveLength(2);
});

test('leak detector flags scores and levels', () => {
  for (const s of ['оцінено на 0.25', 'оцінено Django', 'оцінка: 4', 'оцінка висока', '7/10', '7 / 10', 'Високий',
    'висока', 'низька', 'середня', 'рівень 3', 'рівні', 'level 3', '75 %', '80%'])
    expect(containsScoreLeak(s), s).toBe(true);
});

test('leak detector allows neutral text', () => {
  expect(containsScoreLeak(PANEL_TEXT.llmOff)).toBe(false);
  expect(topicsCountLabel(2, 10)).toBe('2 з 10 тем');
  expect(containsScoreLeak(topicsCountLabel(2, 10))).toBe(false);
});

test('all panel strings (rendered by the UI from PANEL_TEXT) never leak', () => {
  for (const s of allPanelStrings()) expect(containsScoreLeak(s), s).toBe(false);
});
