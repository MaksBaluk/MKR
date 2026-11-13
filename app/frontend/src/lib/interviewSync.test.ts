import { describe, expect, it } from 'vitest';
import { answerAlreadyAccepted, applyAnswer, idempotencyKeyFor } from './interviewSync';
import type { InterviewState, TurnView } from '@/types';

const turn = (over: Partial<TurnView> = {}): TurnView => ({
  id: 't1', sequence: 1, action_id: 'a', action_name: 'A', created_at: null,
  question_text: 'Q?', question_source: 'LLM', answer_text: null, graded: false, ...over,
});
const state = (over: Partial<InterviewState> = {}): InterviewState => ({
  id: 'iv', status: 'ACTIVE', version: 3, turns: [turn()], pending_turn: turn(), topics_used: 1, ...over,
});

describe('applyAnswer', () => {
  it('stores the returned version and answered turn, clears the pending turn', () => {
    const next = applyAnswer(state(), { turn: turn({ answer_text: 'Hi' }), version: 4 });
    expect(next.version).toBe(4);
    expect(next.pending_turn).toBeNull();
    expect(next.turns[0].answer_text).toBe('Hi');
  });

  it('never moves the version backwards (replayed response with an older version)', () => {
    const next = applyAnswer(state({ version: 7 }), { turn: turn({ answer_text: 'Hi' }), version: 4 });
    expect(next.version).toBe(7);
  });

  it('appends the turn when it is not in the list yet', () => {
    const next = applyAnswer(state({ turns: [] }), { turn: turn({ answer_text: 'Hi' }), version: 4 });
    expect(next.turns).toHaveLength(1);
  });
});

describe('answerAlreadyAccepted', () => {
  it('is true when the refetched turn already holds the same answer', () => {
    expect(answerAlreadyAccepted(state({ turns: [turn({ answer_text: ' Hi ' })] }), 't1', 'Hi')).toBe(true);
  });
  it('is false for a still-open turn or a different answer', () => {
    expect(answerAlreadyAccepted(state(), 't1', 'Hi')).toBe(false);
    expect(answerAlreadyAccepted(state({ turns: [turn({ answer_text: 'Other' })] }), 't1', 'Hi')).toBe(false);
    expect(answerAlreadyAccepted(state(), 'missing', 'Hi')).toBe(false);
  });
});

describe('idempotencyKeyFor', () => {
  it('reuses the key for a retry of the same answer and changes it for new text', () => {
    const cache = new Map<string, string>();
    let n = 0;
    const gen = () => `k${++n}`;
    const first = idempotencyKeyFor(cache, 't1', 'Hi', gen);
    expect(idempotencyKeyFor(cache, 't1', ' Hi', gen)).toBe(first);
    expect(idempotencyKeyFor(cache, 't1', 'Hello', gen)).not.toBe(first);
    expect(idempotencyKeyFor(cache, 't2', 'Hi', gen)).not.toBe(first);
  });
});
