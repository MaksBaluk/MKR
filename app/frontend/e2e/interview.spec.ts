import { expect, test } from '@playwright/test';
import { createProfileAndAttempt, registerViaApi, signIn } from './helpers';

// The Evaluator may be unavailable in the stack under test: the answer must still be saved (UNGRADED) and survive a reload.
test('typed answer is saved and the interview resumes from the server after a reload', async ({ page, request }) => {
  const user = await registerViaApi(request);
  const { profileId, attemptId } = await createProfileAndAttempt(request, user.headers);
  await signIn(page, user.token, profileId);
  await page.goto(`/interview/${attemptId}`);

  const box = page.getByPlaceholder('Введіть вашу відповідь…');
  await expect(box).toBeVisible({ timeout: 60_000 });
  const answer = 'Працював із цим на проєкті, налаштовував індекси та транзакції.';
  await box.fill(answer);
  await page.getByRole('button', { name: 'Надіслати' }).click();
  await expect(page.getByText(answer)).toBeVisible({ timeout: 60_000 });

  await page.reload();
  await expect(page.getByText(answer)).toBeVisible({ timeout: 60_000 });
});

test('another user cannot open the interview', async ({ page, request }) => {
  const owner = await registerViaApi(request);
  const { attemptId } = await createProfileAndAttempt(request, owner.headers);
  const intruder = await registerViaApi(request);
  const res = await request.get(`/api/v1/interviews/${attemptId}`, { headers: intruder.headers });
  expect([403, 404]).toContain(res.status());
  await signIn(page, intruder.token);
  await page.goto(`/interview/${attemptId}`);
  await expect(page.getByPlaceholder('Введіть вашу відповідь…')).toHaveCount(0);
});
