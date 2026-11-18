import { expect, type APIRequestContext, type Page } from '@playwright/test';

const API = '/api/v1';

/** Throwaway account through the real API (a fresh user per test keeps tests independent). */
export async function registerViaApi(request: APIRequestContext) {
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const email = `e2e-${stamp}@example.test`;
  const password = `E2e-${stamp}-pw!`;
  const res = await request.post(`${API}/auth/register`, { data: { email, password, display_name: 'E2E' } });
  expect(res.status()).toBe(201);
  const { token } = await res.json();
  return { email, password, token: token as string, headers: { Authorization: `Bearer ${token}` } };
}

export async function createProfileAndAttempt(request: APIRequestContext, headers: Record<string, string>) {
  const p = await request.post(`${API}/profiles`, {
    headers, data: { name: 'E2E профіль', track: 'python', target_level: 'middle', years_experience: 3 },
  });
  expect(p.status()).toBe(201);
  const profile = await p.json();
  const a = await request.post(`${API}/profiles/${profile.id}/attempts`, { headers });
  expect(a.ok()).toBeTruthy();
  return { profileId: profile.id as string, attemptId: (await a.json()).id as string };
}

/** Signs the browser in without touching the login form (token + active profile in localStorage, as the app stores them). */
export async function signIn(page: Page, token: string, profileId?: string) {
  await page.addInitScript(([t, p]) => {
    localStorage.setItem('cm_token', t as string);
    if (p) localStorage.setItem('cm_active_profile', p as string);
  }, [token, profileId ?? null]);
}

export async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}
