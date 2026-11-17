import type { SessionInterview } from '@/lib/navigation';

interface AttemptState {
  open_attempt: { id: string; cohort_id: string; status: string } | null;
  latest_finished_attempt: { id: string; cohort_id: string } | null;
}

/** Interview state of one candidate profile: an open attempt wins, otherwise its latest finished one. */
export function interviewFromProfile(p: AttemptState | null): SessionInterview | null {
  if (!p) return null;
  if (p.open_attempt) return { id: p.open_attempt.id, cohort_id: p.open_attempt.cohort_id, status: 'active' };
  if (p.latest_finished_attempt) {
    return { id: p.latest_finished_attempt.id, cohort_id: p.latest_finished_attempt.cohort_id, status: 'finished' };
  }
  return null;
}
