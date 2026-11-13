import { describe, expect, test } from 'vitest';
import {
  MOBILE_TAB_KEYS, STEPS, isFocusLayout, landingPath, pageTitleFor, resumePath, safeReturnPath, stepForPath, stepStates,
} from '@/lib/navigation';

const active = { id: 'i1', cohort_id: 'c1', status: 'active' as const };
const finished = { id: 'i2', cohort_id: 'c2', status: 'finished' as const };
const byKey = (states: ReturnType<typeof stepStates>) => Object.fromEntries(states.map((s) => [s.step.key, s]));

describe('stepForPath / pageTitleFor', () => {
  test('maps routes to journey steps, including nested vacancy pages', () => {
    expect(stepForPath('/')?.n).toBe(1);
    expect(stepForPath('/profile')?.n).toBe(2);
    expect(stepForPath('/interview/x')?.n).toBe(3);
    expect(stepForPath('/vacancies/42')?.key).toBe('vacancies');
    expect(stepForPath('/vacancies-old')).toBeNull();
    expect(stepForPath('/profiles')).toBeNull();
  });
  test('titles for steps, non-step pages and unknown paths', () => {
    expect(pageTitleFor('/market')).toBe('Профіль ринку');
    expect(pageTitleFor('/profiles')).toBe('Профілі');
    expect(pageTitleFor('/nope')).toBe('Сторінку не знайдено');
  });
  test('six numbered steps and five mobile tabs that exist in STEPS', () => {
    expect(STEPS.map((s) => s.n)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(MOBILE_TAB_KEYS.every((k) => STEPS.some((s) => s.key === k))).toBe(true);
    expect(MOBILE_TAB_KEYS).toHaveLength(5);
  });
});

describe('stepStates', () => {
  test('before any interview only welcome and profile open; nothing after is reachable', () => {
    const s = byKey(stepStates('/', null));
    expect(s.welcome.status).toBe('current');
    expect(s.profile).toMatchObject({ status: 'available', to: '/profile' });
    for (const k of ['interview', 'results', 'vacancies', 'market']) {
      expect(s[k].status).toBe('locked');
      expect(s[k].to).toBeNull();
      expect(s[k].reason).toBeTruthy();
    }
  });
  test('on the profile step the welcome step is marked done', () => {
    const s = byKey(stepStates('/profile', null));
    expect(s.welcome.status).toBe('done');
    expect(s.profile.status).toBe('current');
  });
  test('active interview: profile frozen, interview opens, results still locked', () => {
    const s = byKey(stepStates('/', active));
    expect(s.profile).toMatchObject({ status: 'done', to: null });
    expect(s.interview).toMatchObject({ status: 'available', to: '/interview/i1' });
    expect(s.results.status).toBe('locked');
  });
  test('finished interview unlocks results, vacancies and market', () => {
    const s = byKey(stepStates('/results', finished));
    expect(s.interview).toMatchObject({ status: 'done', to: null });
    expect(s.results.status).toBe('current');
    expect(s.vacancies).toMatchObject({ status: 'available', to: '/vacancies' });
    expect(s.market.to).toBe('/market');
  });
  test('exactly one current step on a step route, none elsewhere', () => {
    expect(stepStates('/interview/i1', active).filter((s) => s.status === 'current')).toHaveLength(1);
    expect(stepStates('/profiles', finished).filter((s) => s.status === 'current')).toHaveLength(0);
  });
});

test('focus layout only for interview routes', () => {
  expect(isFocusLayout('/interview/1')).toBe(true);
  expect(isFocusLayout('/results')).toBe(false);
});

describe('safeReturnPath', () => {
  test('keeps internal paths with query', () => {
    expect(safeReturnPath('/vacancies?page=2')).toBe('/vacancies?page=2');
  });
  test('rejects external, protocol-relative, login and non-strings', () => {
    expect(safeReturnPath('https://evil.test')).toBe('/');
    expect(safeReturnPath('//evil.test')).toBe('/');
    expect(safeReturnPath('/\\evil.test')).toBe('/');
    expect(safeReturnPath('/login')).toBe('/');
    expect(safeReturnPath(undefined)).toBe('/');
  });
});

describe('resume after boot', () => {
  test('resumePath follows interview state', () => {
    expect(resumePath(active)).toBe('/interview/i1');
    expect(resumePath(finished)).toBe('/results');
    expect(resumePath(null)).toBe('/');
  });
  test('landingPath resumes only from the root and keeps deep links', () => {
    expect(landingPath('/', active)).toBe('/interview/i1');
    expect(landingPath('/vacancies', active)).toBe('/vacancies');
    expect(landingPath('/', null)).toBe('/');
  });
});
