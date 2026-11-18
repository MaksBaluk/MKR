import { describe, expect, test } from 'vitest';
import { desiredLabel, explanationLines, groupBySection, levelLabel, SECTIONS, sectionTitle } from '@/lib/levelView';
import type { ResultSection } from '@/types';

describe('level labels', () => {
  test('levelLabel covers all four values', () => {
    expect(levelLabel('JUNIOR')).toBe('Junior');
    expect(levelLabel('MIDDLE')).toBe('Middle');
    expect(levelLabel('SENIOR')).toBe('Senior');
    expect(levelLabel('UNKNOWN')).toBe('Недостатньо даних');
  });

  test('desiredLabel maps profile values and a missing value', () => {
    expect(desiredLabel('junior')).toBe('Junior');
    expect(desiredLabel('middle')).toBe('Middle');
    expect(desiredLabel('senior')).toBe('Senior');
    expect(desiredLabel('lead')).toBe('Lead');
    expect(desiredLabel(null)).toBe('Не вказано');
    expect(desiredLabel('')).toBe('Не вказано');
  });
});

describe('sections', () => {
  const item = (id: string, section: ResultSection) => ({ vacancy_id: id, section });

  test('groupBySection keeps every item and the order inside each section', () => {
    const items = [item('a', 'OTHER_FITTING'), item('b', 'DESIRED_LEVEL'), item('c', 'UNRESOLVED_OR_GAPS'),
      item('d', 'DESIRED_LEVEL'), item('e', 'OTHER_FITTING')];
    const groups = groupBySection(items);
    expect(Object.keys(groups)).toEqual(['DESIRED_LEVEL', 'OTHER_FITTING', 'UNRESOLVED_OR_GAPS']);
    expect(Object.values(groups).flat().length).toBe(items.length);
    expect(groups.DESIRED_LEVEL?.map((i) => i.vacancy_id)).toEqual(['b', 'd']);
    expect(groups.OTHER_FITTING?.map((i) => i.vacancy_id)).toEqual(['a', 'e']);
    expect(groups.UNRESOLVED_OR_GAPS?.map((i) => i.vacancy_id)).toEqual(['c']);
  });

  test('groupBySection omits empty sections and keeps items with a missing section', () => {
    const items = [item('a', 'OTHER_FITTING'), { vacancy_id: 'legacy' } as { vacancy_id: string; section?: ResultSection }];
    const groups = groupBySection(items);
    expect(Object.keys(groups)).toEqual(['OTHER_FITTING', 'UNRESOLVED_OR_GAPS']);
    expect(Object.values(groups).flat().map((i) => i.vacancy_id).sort()).toEqual(['a', 'legacy']);
    expect(groupBySection([])).toEqual({});
  });

  test('sectionTitle strings', () => {
    expect(SECTIONS.map(sectionTitle)).toEqual([
      'Вакансії бажаного рівня',
      'Інші вакансії, що підходять за підтвердженими вимогами',
      'Вакансії з невирішеними або невиконаними критичними вимогами',
    ]);
  });
});

describe('explanationLines', () => {
  test('drops the policy-id line when the note is shown separately', () => {
    const lines = ['Рівень не визначено: для висновку про Junior недостатньо даних.',
      'Політика рівнів python-seniority/v1 є робочим припущенням і потребує експертної валідації.'];
    expect(explanationLines({ explanation: lines, note: 'Потребує експертної валідації' })).toEqual([lines[0]]);
    expect(explanationLines({ explanation: lines, note: null })).toEqual(lines);
  });
});
