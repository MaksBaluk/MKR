import { expect, test } from '@playwright/test';
import { noHorizontalScroll } from './helpers';

test('register through the form, land on the welcome screen, session survives a reload', async ({ page }) => {
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  await page.goto('/login');
  await page.getByRole('button', { name: 'Зареєструватися' }).click();
  await page.getByLabel('Ім’я').fill('E2E Користувач');
  await page.getByLabel('Електронна пошта').fill(`e2e-${stamp}@example.test`);
  await page.getByLabel('Пароль', { exact: true }).fill(`E2e-${stamp}-pw!`);
  await page.getByRole('button', { name: 'Створити акаунт' }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByRole('heading', { name: /CompetenceMatch/ }).first()).toBeVisible();
  await page.reload();
  await expect(page).not.toHaveURL(/\/login/);
});

test('wrong password shows an error and stays on the login page', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Електронна пошта').fill('nobody@example.test');
  await page.getByLabel('Пароль', { exact: true }).fill('wrong-password-123');
  await page.getByRole('button', { name: 'Увійти' }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test('login page has no horizontal scroll on a 375px phone', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/login');
  await expect(page.getByRole('button', { name: 'Увійти' })).toBeVisible();
  await noHorizontalScroll(page);
});
