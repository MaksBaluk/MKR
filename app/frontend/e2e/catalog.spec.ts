import { expect, test } from '@playwright/test';
import { noHorizontalScroll, registerViaApi, signIn } from './helpers';

test('catalog shows provenance: imported Djinni postings and invented fixtures are labelled differently', async ({ page, request }) => {
  const user = await registerViaApi(request);
  await signIn(page, user.token);
  await page.goto('/vacancies');
  await expect(page.getByRole('list', { name: 'Вакансії' }).or(page.locator('[aria-label="Вакансії"]')).first()).toBeVisible({ timeout: 30_000 });
  const res = await request.get('/api/v1/vacancies?page_size=50', { headers: user.headers });
  expect(res.ok()).toBeTruthy();
  const labels = new Set((await res.json()).items.map((i: { source_label: string }) => i.source_label));
  expect([...labels].every((l) => ['Djinni', 'robota.ua', 'work.ua', 'DOU', 'Приклад'].includes(l as string))).toBeTruthy();
});

test('catalog and vacancy list have no horizontal scroll on 375px', async ({ page, request }) => {
  const user = await registerViaApi(request);
  await signIn(page, user.token);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/vacancies');
  await expect(page.locator('[aria-label="Вакансії"]').first()).toBeVisible({ timeout: 30_000 });
  await noHorizontalScroll(page);
});
