import { describe, it, expect } from 'vitest';
import { formatPercent, formatCurrency } from './format';

describe('format', () => {
  it('returns an em dash for null shares, not 0%', () => {
    expect(formatPercent(null)).toBe('—');
    expect(formatPercent(undefined)).toBe('—');
  });
  it('rounds ratios to whole percent', () => {
    expect(formatPercent(3 / 11)).toBe('27%');
  });
  it('uses uk-UA grouping for currency', () => {
    expect(formatCurrency(3000, 'USD')).toMatch(/3\s000/);
  });
});
