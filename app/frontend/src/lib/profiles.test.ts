import { describe, expect, test } from 'vitest';
import {
  activeAfterArchive, attemptStatusLabel, isProfileComplete, profileFormFrom, startLabel, trackLabel, validateProfileForm,
} from '@/lib/profiles';

const ok = {
  name: 'Python-профіль', track: 'python', desired_title: 'Backend', target_level: 'middle', work_mode: 'remote',
  years: '3', location: 'Київ',
};

describe('validateProfileForm', () => {
  test('valid form becomes an API body', () => {
    expect(validateProfileForm(ok)).toEqual({
      errors: {},
      body: {
        name: 'Python-профіль', track: 'python', desired_title: 'Backend', target_level: 'middle', work_mode: 'remote',
        years_experience: 3, location: 'Київ',
      },
    });
  });
  test('empty years means unknown; whitespace is trimmed', () => {
    const r = validateProfileForm({ ...ok, name: '  Ім’я  ', years: ' ', location: '  ' });
    expect(r.body).toMatchObject({ name: 'Ім’я', years_experience: null, location: '' });
  });
  test('Ukrainian messages for each invalid field and no body', () => {
    const r = validateProfileForm({
      name: 'A', track: 'java', desired_title: 'x'.repeat(161), target_level: 'wizard', work_mode: 'moon', years: '2.5',
      location: 'y'.repeat(121),
    });
    expect(r.body).toBeNull();
    expect(r.errors).toEqual({
      name: 'Назва профілю має містити щонайменше 2 символи.',
      track: 'Оберіть напрям.',
      target_level: 'Оберіть рівень.',
      work_mode: 'Оберіть формат роботи.',
      desired_title: 'Бажана посада — до 160 символів.',
      years: 'Вкажіть ціле число років від 0 до 70.',
      location: 'Локація — до 120 символів.',
    });
  });
  test('track, level and work mode may stay unchosen while the profile is being filled in', () => {
    const r = validateProfileForm({ ...ok, track: '', target_level: '', work_mode: '' });
    expect(r.errors).toEqual({});
    expect(r.body).toMatchObject({ track: null, target_level: null, work_mode: null });
  });
  test('years limits match the API', () => {
    expect(validateProfileForm({ ...ok, years: '-1' }).errors.years).toBeTruthy();
    expect(validateProfileForm({ ...ok, years: '71' }).errors.years).toBeTruthy();
    expect(validateProfileForm({ ...ok, years: '70' }).errors.years).toBeUndefined();
    expect(validateProfileForm({ ...ok, years: 'abc' }).errors.years).toBeTruthy();
  });
  test('long name is rejected', () => {
    expect(validateProfileForm({ ...ok, name: 'n'.repeat(121) }).errors.name).toBe('Назва профілю — до 120 символів.');
  });
});

test('profileFormFrom prefills the edit form', () => {
  expect(profileFormFrom({
    name: 'N', track: 'design', desired_title: 'UI', target_level: 'senior', work_mode: 'hybrid', years_experience: null,
    location: 'Lviv',
  })).toEqual({
    name: 'N', track: 'design', desired_title: 'UI', target_level: 'senior', work_mode: 'hybrid', years: '', location: 'Lviv',
  });
  expect(profileFormFrom(null).track).toBe('');
  expect(profileFormFrom(null).target_level).toBe('');
});

test('a profile is complete when track, level and years are set (years 0 counts)', () => {
  expect(isProfileComplete({ track: 'python', target_level: 'junior', years_experience: 0 })).toBe(true);
  expect(isProfileComplete({ track: null, target_level: 'junior', years_experience: 1 })).toBe(false);
  expect(isProfileComplete({ track: 'python', target_level: null, years_experience: 1 })).toBe(false);
  expect(isProfileComplete({ track: 'python', target_level: 'middle', years_experience: null })).toBe(false);
  expect(isProfileComplete(null)).toBe(false);
});

describe('activeAfterArchive', () => {
  const ps = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  test('archiving another profile keeps the active one', () => {
    expect(activeAfterArchive(ps, 'b', 'a')).toBe('a');
  });
  test('archiving the active profile moves to the first remaining one', () => {
    expect(activeAfterArchive(ps, 'a', 'a')).toBe('b');
    expect(activeAfterArchive(ps, 'c', 'c')).toBe('a');
  });
  test('archiving the last profile leaves none', () => {
    expect(activeAfterArchive([{ id: 'a' }], 'a', 'a')).toBeNull();
  });
});

test('status, track and start-button labels', () => {
  expect(['ACTIVE', 'PAUSED', 'FINISHED', 'X'].map(attemptStatusLabel)).toEqual(['Активна', 'Призупинена', 'Завершена', 'X']);
  expect(trackLabel('marketing')).toBe('Маркетинг');
  expect(trackLabel('unknown')).toBe('unknown');
  expect(startLabel(0, [])).toBe('Пройти співбесіду');
  expect(startLabel(2, [{ status: 'FINISHED' }, { status: 'PAUSED' }])).toBe('Продовжити співбесіду');
  expect(startLabel(1, [{ status: 'FINISHED' }])).toBe('Пройти ще раз');
  expect(startLabel(1, null)).toBe('Пройти ще раз');
});

describe('ratingsMap', () => {
  test('keeps unrated and zero values distinct', async () => {
    const { ratingsMap } = await import('@/lib/profiles');
    expect(ratingsMap([{ action_id: 'a', value: 0 }, { action_id: 'b', value: null }])).toEqual({ a: 0, b: null });
    expect(ratingsMap([])).toEqual({});
  });
});
