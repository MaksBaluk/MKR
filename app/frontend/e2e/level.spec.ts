import { expect, test } from '@playwright/test';
import { createProfileAndAttempt, noHorizontalScroll, registerViaApi, signIn } from './helpers';

const API = '/api/v1';
const SECTION_TITLES = [
  'Вакансії бажаного рівня',
  'Інші вакансії, що підходять за підтвердженими вимогами',
  'Вакансії з невирішеними або невиконаними критичними вимогами',
];

// No Evaluator is needed: an attempt finished without answers has no graded criteria, so the level is UNKNOWN.
test('results show desired vs assessed level and sections never hide vacancies', async ({ page, request }) => {
  const user = await registerViaApi(request);
  const { profileId, attemptId } = await createProfileAndAttempt(request, user.headers);
  const iv = await (await request.get(`${API}/interviews/${attemptId}`, { headers: user.headers })).json();
  const fin = await request.post(`${API}/interviews/${attemptId}/finish`, { headers: user.headers, data: { version: iv.version } });
  expect(fin.ok()).toBeTruthy();

  const level = await request.get(`${API}/interviews/${attemptId}/level`, { headers: user.headers });
  expect(level.ok()).toBeTruthy();
  expect((await level.json()).assessed_level).toBe('UNKNOWN');
  const api = await (await request.get(`${API}/profiles/${profileId}/results?page=1&page_size=10&fitting=all`,
    { headers: user.headers })).json();

  expect(api.items.length).toBeGreaterThan(0);
  expect(api.level?.assessed_level).toBe('UNKNOWN');
  await signIn(page, user.token, profileId);
  await page.goto('/results');
  await expect(page.getByText('Бажаний рівень', { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('dd').filter({ hasText: /^Middle$/ })).toBeVisible();
  await expect(page.getByText('Підтверджений рівень', { exact: true })).toBeVisible();
  await expect(page.locator('dd').filter({ hasText: /^Недостатньо даних$/ })).toBeVisible();
  await expect(page.getByText(/%.*(найм|працевлашт)/i)).toHaveCount(0);

  await expect(page.getByText(/місце в загальному списку, упорядкованому за відсотком/)).toBeVisible();

  // Sections are labels over the same page: every vacancy the API returned is shown exactly once.
  const cards = page.getByRole('link', { name: /^Деталі вакансії/ });
  await expect(cards).toHaveCount(api.items.length);
  const keys = ['DESIRED_LEVEL', 'OTHER_FITTING', 'UNRESOLVED_OR_GAPS'];
  const shown = new Set(api.items.map((i: { section: string }) => SECTION_TITLES[keys.indexOf(i.section)]));
  for (const t of SECTION_TITLES)
    await expect(page.getByRole('heading', { name: t, exact: true })).toHaveCount(shown.has(t) ? 1 : 0);
  expect(api.total).toBeGreaterThanOrEqual(api.items.length);

  await page.setViewportSize({ width: 375, height: 812 });
  await noHorizontalScroll(page);
});
