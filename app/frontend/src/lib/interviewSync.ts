import type { InterviewState, TurnView } from '@/types';

/** Response of POST /interviews/:id/answers (fresh or idempotent replay). */
export interface AnswerResponse {
  turn: TurnView;
  version: number;
  replayed?: boolean;
}

/** Applies an accepted answer locally: the server's version wins, but never moves backwards. */
export function applyAnswer(state: InterviewState, res: AnswerResponse): InterviewState {
  const has = state.turns.some((t) => t.id === res.turn.id);
  return {
    ...state,
    version: Math.max(state.version, res.version),
    pending_turn: null,
    turns: has ? state.turns.map((t) => (t.id === res.turn.id ? res.turn : t)) : [...state.turns, res.turn],
  };
}

/** True when a refetched state shows that this exact answer was already stored (e.g. a double submit). */
export function answerAlreadyAccepted(state: InterviewState, turnId: string, text: string): boolean {
  const t = state.turns.find((x) => x.id === turnId);
  return t?.answer_text != null && t.answer_text.trim() === text.trim();
}

/** One idempotency key per (turn, answer text): retries of the same answer replay instead of conflicting. */
export function idempotencyKeyFor(cache: Map<string, string>, turnId: string, text: string,
  gen: () => string = () => crypto.randomUUID()): string {
  const id = `${turnId}\u0000${text.trim()}`;
  let key = cache.get(id);
  if (!key) {
    key = gen();
    cache.set(id, key);
  }
  return key;
}
