import { describe, it, expect } from 'vitest';
import { summarize } from './presentation';

const row = { s: 3, f: 0, u: 8, required_class: 1, match: 1, coverage: 3 / 11, r_score: 3 / 11 };

describe('summarize (presentation only)', () => {
  it('headlines the share of groups with known evidence, not a suitability percent', () => {
    const s = summarize(row);
    expect(s.headline).toBe('3 із 11 вимог відповідають наявним оцінкам (27%)');
    expect(s.coverageLabel).toBe('Оцінено: 27%');
    expect(s.unknownLabel).toBe('Невідомо: 8');
    expect(s.mandatoryLabel).toBe('Обов\'язкові вимоги ще не повністю оцінені');
  });

  it('labels Match as conditional on assessed groups', () => {
    expect(summarize(row).matchLabel).toBe('Серед оцінених вимог: 100% (3/3)');
  });

  it('never shows 0% or 100% when nothing is assessed', () => {
    const empty = summarize({ s: 0, f: 0, u: 4, required_class: 1, match: null, coverage: 0, r_score: 0 });
    expect(empty.matchLabel).toBe('Поки немає оцінених вимог');
    expect(empty.headline).toBe('Поки немає оцінених вимог');
  });

  it('a regression guard: the misleading bare 100% headline never appears', () => {
    const all = JSON.stringify(summarize(row));
    expect(all).not.toMatch(/"headline":"100%/);
    expect(all).not.toMatch(/загальна відповідність/);
  });

  it('a vacancy without requirements says so, not "no evidence yet"', () => {
    const none = summarize({ s: 0, f: 0, u: 0, required_class: 2, match: null, coverage: null, r_score: null });
    expect(none.headline).toBe('У вакансії немає вимог для оцінки');
  });
});
