import { expect, test } from 'vitest';
import { isChunkLoadError } from '@/lib/errors';

test('recognises failed dynamic imports across browsers', () => {
  expect(isChunkLoadError(new TypeError('Failed to fetch dynamically imported module: /assets/x.js'))).toBe(true);
  expect(isChunkLoadError(new TypeError('Importing a module script failed.'))).toBe(true);
  expect(isChunkLoadError(new Error('error loading dynamically imported module'))).toBe(true);
  expect(isChunkLoadError(Object.assign(new Error('x'), { name: 'ChunkLoadError' }))).toBe(true);
});

test('other errors and non-errors are not chunk errors', () => {
  expect(isChunkLoadError(new Error('Cannot read properties of undefined'))).toBe(false);
  expect(isChunkLoadError('Failed to fetch dynamically imported module')).toBe(false);
  expect(isChunkLoadError(null)).toBe(false);
});
