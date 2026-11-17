import { describe, expect, test } from 'vitest';
import {
  MOBILE_TAB_KEYS, STEPS, isFocusLayout, landingPath, mobileTabs, pageTitleFor, resumePath, safeReturnPath,
  progressPercent, progressSteps, sideStates, stepForPath, stepStates,
} from '@/lib/navigation';

const active = { id: 'i1', cohort_id: 'c1', status: 'active' as const };
const finished = { id: 'i2', cohort_id: 'c2', status: 'finished' as const };
const byKey = (states: ReturnType<typeof stepStates>) => Object.fromEntries(states.map((s) => [s.step.key, s]));
const sideByKey = (pathname: string) => Object.fromEntries(sideStates(pathname).map((s) => [s.key, s]));

describe('stepForPath / pageTitleFor', () => {
  test('maps routes to journey steps', () => {
    expect(stepForPath('/')?.n).toBe(1);
    expect(stepForPath('/profile')?.n).toBe(2);
    expect(stepForPath('/interview/x')?.n).toBe(3);
    expect(stepForPath('/results')?.n).toBe(4);
    expect(stepForPath('/market')?.n).toBe(5);
    expect(stepForPath('/profiles')).toBeNull();
  });
  test('vacancies are a side item, not a step', () => {
    expect(stepForPath('/vacancies')).toBeNull();
    expect(stepForPath('/vacancies/42')).toBeNull();
    expect(stepForPath('/vacancies-old')).toBeNull();
  });
  test('titles for steps, side items, non-step pages and unknown paths', () => {
    expect(pageTitleFor('/market')).toBe('Профіль ринку');
    expect(pageTitleFor('/vacancies')).toBe('Вакансії');
    expect(pageTitleFor('/profiles')).toBe('Профілі');
    expect(pageTitleFor('/nope')).toBe('Сторінку не знайдено');
  });
  test('five numbered steps, and mobile tabs cover steps plus vacancies', () => {
    expect(STEPS.map((s) => s.n)).toEqual([1, 2, 3, 4, 5]);
    expect(STEPS.map((s) => s.key)).toEqual(['welcome', 'profile', 'interview', 'results', 'market']);
    expect(MOBILE_TAB_KEYS).toEqual(['welcome', 'interview', 'results', 'vacancies', 'market']);
    expect(mobileTabs('/', null).map((t) => t.key)).toEqual(MOBILE_TAB_KEYS);
  });
});

describe('stepStates', () => {
  test('exactly the five journey steps, vacancies never among them', () => {
    expect(stepStates('/', null).map((s) => s.step.key)).toEqual(['welcome', 'profile', 'interview', 'results', 'market']);
  });
  test('before any interview only welcome and profile open', () => {
    const s = byKey(stepStates('/', null));
    expect(s.welcome.status).toBe('current');
    expect(s.profile).toMatchObject({ status: 'available', to: '/profile' });
    for (const k of ['interview', 'results', 'market']) {
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
  test('active interview: profile done but still linked, interview opens, results still locked', () => {
    const s = byKey(stepStates('/', active));
    expect(s.profile).toMatchObject({ status: 'done', to: '/profile', reason: null });
    expect(s.interview).toMatchObject({ status: 'available', to: '/interview/i1' });
    expect(s.results.status).toBe('locked');
    expect(s.market.status).toBe('locked');
  });
  test('finished interview unlocks results and market', () => {
    const s = byKey(stepStates('/results', finished));
    expect(s.interview).toMatchObject({ status: 'done', to: null });
    expect(s.profile).toMatchObject({ status: 'done', to: '/profile' });
    expect(s.results.status).toBe('current');
    expect(s.market.to).toBe('/market');
  });
  test('after the interview every step is done, results and market included (green checks)', () => {
    const s = byKey(stepStates('/', finished));
    expect(Object.values(s).map((x) => x.status)).toEqual(['current', 'done', 'done', 'done', 'done']);
    expect(s.results).toMatchObject({ status: 'done', to: '/results' });
    expect(s.market).toMatchObject({ status: 'done', to: '/market' });
  });
  test('results and market are not done while the interview is open', () => {
    const s = byKey(stepStates('/', active));
    expect(s.results.status).toBe('locked');
    expect(s.market.status).toBe('locked');
  });
  test('exactly one current step on a step route, none elsewhere', () => {
    expect(stepStates('/interview/i1', active).filter((s) => s.status === 'current')).toHaveLength(1);
    expect(stepStates('/profiles', finished).filter((s) => s.status === 'current')).toHaveLength(0);
  });
});

describe('side items', () => {
  test('vacancies and settings are always available, never locked, before or after the interview', () => {
    for (const [path, iv] of [['/', null], ['/', active], ['/results', finished]] as const) {
      const side = sideByKey(path);
      expect(side.vacancies.to).toBe('/vacancies');
      expect(side.vacancies.status).not.toBe('locked');
      expect(side.settings.status).not.toBe('locked');
      expect(mobileTabs(path, iv).find((t) => t.key === 'vacancies')?.status).not.toBe('locked');
    }
  });
  test('current side item is marked current on its own page', () => {
    expect(sideByKey('/vacancies/42').vacancies.status).toBe('current');
    expect(sideByKey('/results').vacancies.status).toBe('available');
  });
  test('settings is a side item with its own page', () => {
    expect(sideByKey('/').settings.label).toBe('Налаштування');
    expect(sideByKey('/').settings.to).toBe('/settings');
    expect(sideByKey('/settings').settings.status).toBe('current');
    expect(pageTitleFor('/settings')).toBe('Налаштування');
    expect(stepForPath('/settings')).toBeNull();
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
  test('landingPath after login never enters the interview; resume stays a button', () => {
    expect(landingPath('/')).toBe('/');
    expect(landingPath('/interview/i1')).toBe('/');
    expect(landingPath('/interview/i1?x=1')).toBe('/');
    expect(landingPath('/vacancies?page=2')).toBe('/vacancies?page=2');
    expect(landingPath('/profile')).toBe('/profile');
  });
});

describe('progress follows the profile, not the open page', () => {
  test('a new account has only seen the welcome step', () => {
    expect(progressSteps(null, false)).toBe(1);
    expect(progressPercent(null, false)).toBe(20);
  });
  test('a complete profile is the second step', () => {
    expect(progressSteps(null, true)).toBe(2);
    expect(progressPercent(null, true)).toBe(40);
  });
  test('an open interview is the third step', () => {
    expect(progressSteps(active, true)).toBe(3);
    expect(progressPercent(active, true)).toBe(60);
  });
  test('a finished interview means everything is done', () => {
    expect(progressSteps(finished, true)).toBe(5);
    expect(progressPercent(finished, true)).toBe(100);
  });
});

describe('landingAfterAuth', () => {
  test('a new account always starts on the welcome page', async () => {
    const { landingAfterAuth } = await import('@/lib/navigation');
    expect(landingAfterAuth('register', '/profile')).toBe('/');
    expect(landingAfterAuth('register', '/results')).toBe('/');
  });
  test('sign-in keeps the requested page but never opens an interview directly', async () => {
    const { landingAfterAuth } = await import('@/lib/navigation');
    expect(landingAfterAuth('login', '/results')).toBe('/results');
    expect(landingAfterAuth('login', '/interview/i1')).toBe('/');
  });
});
