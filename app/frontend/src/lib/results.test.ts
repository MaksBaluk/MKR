import { describe, expect, test } from 'vitest';
import {
  assessedLabel, comparisonRows, DEFAULT_FILTERS, filtersFromQuery, filtersToQuery, fitLabel,
  hasActiveFilters, pageRange, resultsApiPath, totalPages,
} from '@/lib/results';

describe('filters <-> query string', () => {
  test('defaults produce an empty query', () => {
    expect(filtersToQuery(DEFAULT_FILTERS).toString()).toBe('');
    expect(filtersFromQuery(new URLSearchParams(''))).toEqual(DEFAULT_FILTERS);
  });

  test('round trip keeps every filter', () => {
    const f = { work_mode: 'REMOTE', seniority: 'SENIOR', q: 'python api', min_share: 50, page: 3 };
    expect(filtersFromQuery(filtersToQuery(f))).toEqual(f);
  });

  test('invalid values fall back to defaults', () => {
    const f = filtersFromQuery(new URLSearchParams('work_mode=moon&seniority=x&min_share=33&page=-2&q=%20%20'));
    expect(f).toEqual(DEFAULT_FILTERS);
    expect(filtersFromQuery(new URLSearchParams('page=abc')).page).toBe(1);
    expect(filtersFromQuery(new URLSearchParams('work_mode=remote')).work_mode).toBe('REMOTE');
  });

  test('api path uses server param names and omits defaults', () => {
    expect(resultsApiPath('p1', DEFAULT_FILTERS, 10)).toBe('/profiles/p1/results?page=1&page_size=10&fitting=all');
    const path = resultsApiPath('p 1', { work_mode: 'HYBRID', seniority: '', q: 'дані', min_share: 25, page: 2 }, 10);
    expect(path.startsWith('/profiles/p%201/results?')).toBe(true);
    const sp = new URLSearchParams(path.split('?')[1]);
    expect(Object.fromEntries(sp)).toEqual({ page: '2', page_size: '10', fitting: 'all', work_mode: 'HYBRID', q: 'дані', min_share: '25' });
  });

  test('active filters ignore the page', () => {
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, page: 4 })).toBe(false);
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, min_share: 25 })).toBe(true);
  });
});

describe('pagination', () => {
  test('total pages', () => {
    expect(totalPages(0, 10)).toBe(0);
    expect(totalPages(10, 10)).toBe(1);
    expect(totalPages(11, 10)).toBe(2);
  });

  test('short ranges list every page', () => {
    expect(pageRange(1, 1)).toEqual([1]);
    expect(pageRange(2, 5)).toEqual([1, 2, 3, 4, 5]);
  });

  test('long ranges collapse with gaps around the current page', () => {
    expect(pageRange(1, 10)).toEqual([1, 2, 'gap', 10]);
    expect(pageRange(5, 10)).toEqual([1, 'gap', 4, 5, 6, 'gap', 10]);
    expect(pageRange(10, 10)).toEqual([1, 'gap', 9, 10]);
    expect(pageRange(3, 10)).toEqual([1, 2, 3, 4, 'gap', 10]);
  });
});

describe('fit labels', () => {
  test('fit percentage', () => {
    expect(fitLabel(18)).toBe('Збіг профілю 18%');
    expect(fitLabel(0)).toBe('Збіг профілю 0%');
  });

  test('assessed requirements in grammatical Ukrainian', () => {
    expect(assessedLabel(2, 11)).toBe('оцінено 2 із 11 вимог');
    expect(assessedLabel(0, 1)).toBe('оцінено 0 із 1 вимоги');
    expect(assessedLabel(3, 21)).toBe('оцінено 3 із 21 вимоги');
    expect(assessedLabel(5, 12)).toBe('оцінено 5 із 12 вимог');
  });
});

test('vacancyCount uses Ukrainian plural forms', async () => {
  const { vacancyCount } = await import('@/lib/results');
  expect([1, 3, 5, 11, 21, 22, 112].map(vacancyCount)).toEqual([
    'Знайдено 1 вакансію', 'Знайдено 3 вакансії', 'Знайдено 5 вакансій', 'Знайдено 11 вакансій',
    'Знайдено 21 вакансію', 'Знайдено 22 вакансії', 'Знайдено 112 вакансій',
  ]);
});

describe('comparisonRows', () => {
  test('keeps server order and passes nulls through without inventing values', () => {
    const rows = comparisonRows([
      { action_name: 'Б', interview_score: 0.5, self_rating: null },
      { action_name: 'А', interview_score: null, self_rating: 0.8 },
    ]);
    expect(rows).toEqual([
      { name: 'Б', interview: 0.5, self: null },
      { name: 'А', interview: null, self: 0.8 },
    ]);
  });
});
