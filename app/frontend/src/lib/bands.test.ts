import { expect, test } from 'vitest';
import { bandFor, initials } from '@/lib/bands';

test('band endpoints', () => {
  expect(bandFor(0.75).label).toBe('Високий');
  expect(bandFor(0.5).label).toBe('Середній');
  expect(bandFor(0.49).label).toBe('Низький');
});

test('initials', () => {
  expect(initials('Іван Петренко')).toBe('ІП');
  expect(initials('  ')).toBe('?');
});
