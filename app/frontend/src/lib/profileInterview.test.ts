import { describe, expect, test } from 'vitest';
import { interviewFromProfile } from '@/lib/profileInterview';

const base = { open_attempt: null, latest_finished_attempt: null };

describe('interviewFromProfile', () => {
  test('profile without attempts has no interview', () => {
    expect(interviewFromProfile(base)).toBeNull();
    expect(interviewFromProfile(null)).toBeNull();
  });

  test('an open attempt wins over a finished one', () => {
    const p = {
      open_attempt: { id: 'a2', cohort_id: 'c2', status: 'ACTIVE' },
      latest_finished_attempt: { id: 'a1', cohort_id: 'c1' },
    };
    expect(interviewFromProfile(p)).toEqual({ id: 'a2', cohort_id: 'c2', status: 'active' });
  });

  test('paused attempt is still an open interview', () => {
    expect(interviewFromProfile({ ...base, open_attempt: { id: 'a3', cohort_id: 'c3', status: 'PAUSED' } }))
      .toEqual({ id: 'a3', cohort_id: 'c3', status: 'active' });
  });

  test('only a finished attempt gives a finished interview', () => {
    expect(interviewFromProfile({ ...base, latest_finished_attempt: { id: 'a1', cohort_id: 'c1' } }))
      .toEqual({ id: 'a1', cohort_id: 'c1', status: 'finished' });
  });
});
