import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { ApiError, api, onUnauthorized, setToken } from '@/api';

function respond(status: number) {
  return vi.fn(async () => new Response(JSON.stringify({ detail: 'x' }), { status, headers: { 'Content-Type': 'application/json' } }));
}

let handler: ReturnType<typeof vi.fn>;
let unregister: () => void;

beforeEach(() => {
  handler = vi.fn();
  unregister = onUnauthorized(handler);
});

afterEach(() => {
  unregister();
  vi.unstubAllGlobals();
});

test('401 from an authenticated call fires the handler and still rejects', async () => {
  vi.stubGlobal('fetch', respond(401));
  await expect(api('/profile')).rejects.toMatchObject({ status: 401 });
  expect(handler).toHaveBeenCalledTimes(1);
});

test('401 from login/register is a wrong-credentials error, not an expired session', async () => {
  vi.stubGlobal('fetch', respond(401));
  await expect(api('/auth/login', { method: 'POST', json: {} })).rejects.toBeInstanceOf(ApiError);
  await expect(api('/auth/register', { method: 'POST', json: {} })).rejects.toBeInstanceOf(ApiError);
  expect(handler).not.toHaveBeenCalled();
});

test('parallel 401s fire the handler once', async () => {
  vi.stubGlobal('fetch', respond(401));
  await Promise.allSettled([api('/profile'), api('/assessments'), api('/recommendations', { method: 'POST', json: {} })]);
  expect(handler).toHaveBeenCalledTimes(1);
});

test('a new token re-arms the handler for the next session', async () => {
  vi.stubGlobal('fetch', respond(401));
  await api('/profile').catch(() => undefined);
  setToken('fresh');
  await api('/profile').catch(() => undefined);
  expect(handler).toHaveBeenCalledTimes(2);
  setToken(null);
});

test('other errors do not fire the handler', async () => {
  vi.stubGlobal('fetch', respond(500));
  await expect(api('/profile')).rejects.toMatchObject({ status: 500 });
  expect(handler).not.toHaveBeenCalled();
});
