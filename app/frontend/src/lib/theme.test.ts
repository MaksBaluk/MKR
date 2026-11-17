import { describe, expect, test } from 'vitest';
import { normalizeTheme, resolveTheme } from '@/lib/theme';

describe('theme', () => {
  test('only known values are accepted, everything else is system', () => {
    expect(normalizeTheme('dark')).toBe('dark');
    expect(normalizeTheme('light')).toBe('light');
    expect(normalizeTheme('system')).toBe('system');
    expect(normalizeTheme('purple')).toBe('system');
    expect(normalizeTheme(null)).toBe('system');
  });

  test('system follows the device preference', () => {
    expect(resolveTheme('system', true)).toBe('dark');
    expect(resolveTheme('system', false)).toBe('light');
  });

  test('explicit choice ignores the device preference', () => {
    expect(resolveTheme('light', true)).toBe('light');
    expect(resolveTheme('dark', false)).toBe('dark');
  });
});
