import { describe, expect, test } from 'vitest';
import { profileFormFrom } from '@/lib/profiles';
import { profileSummary } from '@/lib/profileSummary';

describe('profileSummary', () => {
  test('empty form: nothing filled, not ready', () => {
    const s = profileSummary(profileFormFrom(null));
    expect(s.percent).toBe(0);
    expect(s.ready).toBe(false);
    expect(s.rows.every((r) => r.value === null)).toBe(true);
  });
  test('required three filled makes it ready at 50%', () => {
    const s = profileSummary({ ...profileFormFrom(null), track: 'python', target_level: 'middle', years: '4' });
    expect(s.ready).toBe(true);
    expect(s.percent).toBe(50);
    expect(s.rows.find((r) => r.key === 'years')?.value).toBe('4 роки');
  });
  test('all filled gives 100% and Ukrainian year forms', () => {
    const f = { name: 'n', track: 'design', desired_title: 'Дизайнер', target_level: 'senior', work_mode: 'remote', years: '1', location: ' Київ ' };
    const s = profileSummary(f);
    expect(s.percent).toBe(100);
    expect(s.rows.find((r) => r.key === 'years')?.value).toBe('1 рік');
    expect(s.rows.find((r) => r.key === 'location')?.value).toBe('Київ');
    expect(profileSummary({ ...f, years: '11' }).rows[2].value).toBe('11 років');
    expect(profileSummary({ ...f, years: '22' }).rows[2].value).toBe('22 роки');
  });
});
