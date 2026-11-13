import { expect, test } from 'vitest';
import { pickActiveId } from '@/lib/activeProfileSelect';

const ps = [{ id: 'p1' }, { id: 'p2' }];

test('remembered profile wins when it still exists', () => {
  expect(pickActiveId(ps, 'p2')).toBe('p2');
});

test('falls back to the first profile', () => {
  expect(pickActiveId(ps, 'gone')).toBe('p1');
  expect(pickActiveId(ps, null)).toBe('p1');
});

test('no profiles means no active profile', () => {
  expect(pickActiveId([], 'p1')).toBeNull();
});
