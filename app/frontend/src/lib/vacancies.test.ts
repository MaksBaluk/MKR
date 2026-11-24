import { describe, expect, test } from 'vitest';
import {
  DEFAULT_VACANCY_FILTERS, backToListPath, employmentLabel, formatSalary, hasVacancyFilters, kindLabel, levelWord,
  missingFromDescription, parseDescription, stackPreview, vacanciesApiPath, vacancyFiltersFromQuery,
  vacancyFiltersToQuery, yearsCount, yearsLabel,
} from '@/lib/vacancies';

const NBSP = ' ';

describe('vacancy filters <-> query string', () => {
  test('empty query gives defaults', () => {
    expect(vacancyFiltersFromQuery(new URLSearchParams())).toEqual(DEFAULT_VACANCY_FILTERS);
  });
  test('round trip keeps every valid value and omits defaults', () => {
    const f = { track: 'design', work_mode: 'REMOTE', seniority: 'SENIOR', location: 'Lviv', salary_min: 3000,
      q: 'figma', sort: 'salary_desc', page: 3 } as const;
    const sp = vacancyFiltersToQuery(f);
    expect(vacancyFiltersFromQuery(sp)).toEqual(f);
    expect(vacancyFiltersToQuery(DEFAULT_VACANCY_FILTERS).toString()).toBe('');
  });
  test('invalid values fall back to defaults instead of reaching the API', () => {
    const f = vacancyFiltersFromQuery(new URLSearchParams(
      'track=java&work_mode=moon&seniority=god&salary_min=-5&sort=random&page=0&q=%20%20x%20'));
    expect(f).toEqual({ ...DEFAULT_VACANCY_FILTERS, q: 'x' });
    expect(vacancyFiltersFromQuery(new URLSearchParams('salary_min=1234&page=2.5')).salary_min).toBe(0);
    expect(vacancyFiltersFromQuery(new URLSearchParams('page=2.5')).page).toBe(1);
  });
  test('enum values are case-insensitive in the URL', () => {
    const f = vacancyFiltersFromQuery(new URLSearchParams('track=Python&work_mode=remote&seniority=junior'));
    expect(f).toMatchObject({ track: 'python', work_mode: 'REMOTE', seniority: 'JUNIOR' });
  });
  test('long text is trimmed and capped', () => {
    const f = vacancyFiltersFromQuery(new URLSearchParams({ q: 'a'.repeat(300), location: 'b'.repeat(300) }));
    expect(f.q).toHaveLength(120);
    expect(f.location).toHaveLength(80);
  });
  test('API path carries filters, sort and page size; defaults are not sent', () => {
    expect(vacanciesApiPath(DEFAULT_VACANCY_FILTERS, 20)).toBe('/vacancies?page=1&page_size=20&sort=title');
    const p = vacanciesApiPath({ ...DEFAULT_VACANCY_FILTERS, track: 'python', location: 'Київ', salary_min: 2000, q: 'a&b' }, 20);
    const sp = new URLSearchParams(p.split('?')[1]);
    expect(sp.get('track')).toBe('python');
    expect(sp.get('location')).toBe('Київ');
    expect(sp.get('salary_min')).toBe('2000');
    expect(sp.get('q')).toBe('a&b');
  });
  test('hasVacancyFilters ignores sort and page', () => {
    expect(hasVacancyFilters({ ...DEFAULT_VACANCY_FILTERS, sort: 'newest', page: 4 })).toBe(false);
    expect(hasVacancyFilters({ ...DEFAULT_VACANCY_FILTERS, location: 'Lviv' })).toBe(true);
  });
});

describe('labels', () => {
  test('level words come from one mapping', () => {
    expect([1, 2, 3].map(levelWord)).toEqual(['Базовий', 'Середній', 'Просунутий']);
    expect(levelWord(7)).toBe('Рівень 7');
  });
  test('requirement kinds', () => {
    expect(kindLabel('MANDATORY')).toBe('Обов’язкова');
    expect(kindLabel('DESIRED')).toBe('Бажана');
    expect(kindLabel('OTHER')).toBe('OTHER');
  });
  test('employment labels with raw fallback', () => {
    expect(employmentLabel('Full-time')).toBe('Повна зайнятість');
    expect(employmentLabel('Contract')).toBe('Контракт');
    expect(employmentLabel('Freelance')).toBe('Freelance');
    expect(employmentLabel(null)).toBeNull();
  });
  test('years of experience with Ukrainian plural forms', () => {
    expect(yearsLabel(2, 4)).toBe('2–4 роки');
    expect(yearsLabel(5, 6)).toBe('5–6 років');
    expect(yearsLabel(1, null)).toBe('від 1 року');
    expect(yearsLabel(6, null)).toBe('від 6 років');
    expect(yearsLabel(null, 3)).toBe('до 3 років');
    expect(yearsLabel(0, 1)).toBe('до 1 року');
    expect(yearsLabel(null, null)).toBeNull();
    expect(yearsLabel(0, null)).toBeNull();
  });
  test('years count', () => {
    expect([0, 1, 3, 5, 11, 21].map(yearsCount)).toEqual(['0 років', '1 рік', '3 роки', '5 років', '11 років', '21 рік']);
  });
  test('stack preview shows first five and the rest as a count', () => {
    expect(stackPreview(['a', 'b', 'c'])).toEqual({ shown: ['a', 'b', 'c'], rest: 0 });
    expect(stackPreview(['1', '2', '3', '4', '5', '6', '7'])).toEqual({ shown: ['1', '2', '3', '4', '5'], rest: 2 });
    expect(stackPreview(null)).toEqual({ shown: [], rest: 0 });
  });
});

describe('formatSalary', () => {
  test('range with currency and thousands separator', () => {
    expect(formatSalary(4950, 7200, 'EUR')).toBe(`4${NBSP}950–7${NBSP}200 EUR`);
  });
  test('open ranges and equal bounds', () => {
    expect(formatSalary(2000, null, 'USD')).toBe(`від 2${NBSP}000 USD`);
    expect(formatSalary(null, 900, 'USD')).toBe('до 900 USD');
    expect(formatSalary(1500, 1500, 'USD')).toBe(`1${NBSP}500 USD`);
  });
  test('no salary or no currency', () => {
    expect(formatSalary(null, null, 'USD')).toBeNull();
    expect(formatSalary(1000, 2000, null)).toBe(`1${NBSP}000–2${NBSP}000`);
  });
});

describe('parseDescription', () => {
  const text = [
    'Backend Engineer | NovaRidge',
    '',
    'Про команду',
    'Ми будуємо сервіси.',
    'Друге речення окремим рядком.',
    '',
    'Завдання на посаді',
    '- Писати API.',
    '- Тестувати.',
    '',
    'Досвід: від 2 років.',
  ].join('\n');

  test('headings, bullets and paragraphs; title line skipped', () => {
    expect(parseDescription(text, 'Backend Engineer')).toEqual([
      { type: 'heading', text: 'Про команду' },
      { type: 'paragraph', text: 'Ми будуємо сервіси.' },
      { type: 'paragraph', text: 'Друге речення окремим рядком.' },
      { type: 'heading', text: 'Завдання на посаді' },
      { type: 'list', items: ['Писати API.', 'Тестувати.'] },
      { type: 'paragraph', text: 'Досвід: від 2 років.' },
    ]);
  });
  test('title line is kept when it does not repeat the title', () => {
    expect(parseDescription('Інший рядок | X', 'Backend')[0]).toEqual({ type: 'paragraph', text: 'Інший рядок | X' });
  });
  test('empty and whitespace-only input give nothing', () => {
    expect(parseDescription('', 'T')).toEqual([]);
    expect(parseDescription('  \n\n \r\n', 'T')).toEqual([]);
    expect(parseDescription(null, 'T')).toEqual([]);
  });
  test('CRLF, extra blank lines and bullet styles', () => {
    expect(parseDescription('Умови\r\n• Перше\r\n* Друге\r\n\r\n\r\n\r\nКінець.', 'T')).toEqual([
      { type: 'heading', text: 'Умови' },
      { type: 'list', items: ['Перше', 'Друге'] },
      { type: 'paragraph', text: 'Кінець.' },
    ]);
  });
  test('a block that starts with a bullet has no heading; a long first line is not a heading', () => {
    expect(parseDescription('- a\n- b', 'T')).toEqual([{ type: 'list', items: ['a', 'b'] }]);
    const long = 'x'.repeat(90);
    expect(parseDescription(`${long}\nmore`, 'T')[0]).toEqual({ type: 'paragraph', text: long });
    expect(parseDescription('Речення з крапкою.\nще', 'T')[0].type).toBe('paragraph');
  });
  test('HTML-looking text stays plain text', () => {
    const nodes = parseDescription('<script>alert(1)</script>\n- <b>x</b>', 'T');
    expect(nodes).toEqual([
      { type: 'heading', text: '<script>alert(1)</script>' },
      { type: 'list', items: ['<b>x</b>'] },
    ]);
  });
});

test('missingFromDescription returns only items not already in the text', () => {
  expect(missingFromDescription('- Писати API.\n- Тестувати.', ['Писати API.', 'Тестувати.'])).toEqual([]);
  expect(missingFromDescription('', ['A'])).toEqual(['A']);
  expect(missingFromDescription('A', null)).toEqual([]);
});

describe('backToListPath', () => {
  test('restores the list query string from router state', () => {
    expect(backToListPath({ fromList: '/vacancies?track=python&page=2' })).toBe('/vacancies?track=python&page=2');
  });
  test('anything else falls back to the plain list', () => {
    expect(backToListPath(null)).toBe('/vacancies');
    expect(backToListPath({ fromList: '//evil.test' })).toBe('/vacancies');
    expect(backToListPath({ fromList: '/results' })).toBe('/vacancies');
    expect(backToListPath({ fromList: 42 })).toBe('/vacancies');
  });
});

import { postingExcerpts } from '@/lib/vacancies';

describe('postingExcerpts', () => {
  test('unique, trimmed, mandatory first, skipping phrases the description has', () => {
    const groups = [
      { kind: 'DESIRED', excerpt: 'Nice to have SQL.' },
      { kind: 'MANDATORY', excerpt: 'Analytics tools: GA, Tableau;' },
      { kind: 'MANDATORY', excerpt: 'Analytics tools: GA, Tableau;' },
      { kind: 'MANDATORY', excerpt: 'Already in text' },
      { kind: 'MANDATORY', excerpt: '  ' },
    ];
    expect(postingExcerpts(groups, 'Опис. already in text.')).toEqual([
      { kind: 'MANDATORY', text: 'Analytics tools: GA, Tableau' }, { kind: 'DESIRED', text: 'Nice to have SQL.' },
    ]);
  });
});
