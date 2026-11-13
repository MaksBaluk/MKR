import { test, expect, type Page } from '@playwright/test';

async function register(page: Page) {
  const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  await page.goto('/');
  await page.getByRole('button', { name: 'Зареєструватися' }).first().click();
  await page.getByLabel("Ім'я").fill('Олена Тестова');
  await page.getByLabel('Електронна пошта').fill(email);
  await page.getByLabel('Пароль (не менше 10 символів)').fill('long-password-789');
  await page.getByRole('button', { name: 'Зареєструватися' }).last().click();
}

test('candidate: automatic recommendations → typed interview → resume → results', async ({ page }) => {
  await register(page);

  // 1. Recommendations appear with no vacancy selection.
  await expect(page.getByRole('heading', { name: 'Рекомендовані вакансії' })).toBeVisible();
  await expect(page.getByRole('button', { name: "Почати інтерв'ю з усіма 30 вакансіями" })).toBeVisible();
  await expect(page.getByRole('checkbox')).toHaveCount(1); // only the "respect experience" filter

  // 2. Start the shared interview: the cohort is frozen automatically.
  await page.getByRole('button', { name: "Почати інтерв'ю з усіма 30 вакансіями" }).click();
  await expect(page.getByRole('heading', { name: 'Адаптивне інтервю' })).toBeVisible();
  const answer = page.getByLabel('Ваша відповідь');
  await expect(answer).toBeVisible();
  await expect(page.getByRole('radio')).toHaveCount(0); // free text by default, no forced options

  // 3. Typed answer is saved as pending evaluation, not as a score.
  await answer.fill('Перевіряю логи та метрики після кожного релізу і записую висновки');
  await page.getByRole('button', { name: 'Надіслати відповідь' }).click();
  await expect(page.getByText('Відповідь збережено').first()).toBeVisible();
  await expect(page.getByText('Очікує оцінювання').first()).toBeVisible();

  // 4. Reload resumes the same interview.
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Адаптивне інтервю' })).toBeVisible();
  await expect(page.getByText(/Питання \d+ з 8/)).toBeVisible();

  // 5. Finish, then results are the same frozen cohort, with honest headline wording.
  await page.getByRole('button', { name: 'Завершити інтервю' }).click();
  await page.getByRole('button', { name: 'Переглянути результати' }).click();
  await expect(page.getByRole('tab', { name: "Після інтерв'ю" })).toBeVisible();
  // A new candidate has no self-ratings yet, so nothing is evaluable: the UI must say so, not show 0% or 100%.
  await expect(page.getByText('Поки немає оцінених вимог').first()).toBeVisible();
  await expect(page.getByText('Невідомо:', { exact: false }).first()).toBeVisible();
});

test('mobile 375px: no horizontal page scroll on the main screens', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await register(page);
  await expect(page.getByRole('heading', { name: 'Рекомендовані вакансії' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test('settings state: LLM disabled is shown honestly and catalog is labelled as synthetic', async ({ page }) => {
  await register(page);
  await expect(page.getByRole('heading', { name: 'Рекомендовані вакансії' })).toBeVisible();
  await page.getByRole('button', { name: 'Налаштування' }).click();
  await expect(page.getByText('Не налаштовано')).toBeVisible();
  await expect(page.getByText('Навчальний каталог синтетичних вакансій', { exact: false }).first()).toBeVisible();
});
