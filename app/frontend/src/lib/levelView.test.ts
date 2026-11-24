import { describe, expect, test } from 'vitest';
import { desiredLabel, explanationLines, explanationWithoutHigher, hasHigherEvidence, higherEvidenceText, higherNotice, levelLabel, sectionBadge, unassessedItems } from '@/lib/levelView';
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
  test('sectionBadge gives a short label and treats a missing section as gaps', () => {
    expect(sectionBadge('DESIRED_LEVEL')).toBe('бажаний рівень');
    expect(sectionBadge('OTHER_FITTING')).toBe('інші, що підходять');
    expect(sectionBadge('UNRESOLVED_OR_GAPS')).toBe('є прогалини');
    expect(sectionBadge(undefined)).toBe('є прогалини');
    expect(sectionBadge('NEW_VALUE' as ResultSection)).toBe('є прогалини');
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

describe('unassessedItems', () => {
  const crit = [{ id: 'postgresql.indexes', title: 'Індекси та плани виконання', kind: 'COMPETENCY' as const }];
  test('pooled policy (v2) lists capabilities by Ukrainian title', () => {
    const pools = [{ id: 'concurrency', title: 'Конкурентний доступ і паралельність' }];
    expect(unassessedItems({ unassessed_criteria: crit, unassessed_pools: pools })).toEqual(pools);
  });
  test('v1 rows and older payloads fall back to criteria', () => {
    expect(unassessedItems({ unassessed_criteria: crit, unassessed_pools: [] })).toEqual(crit);
    expect(unassessedItems({ unassessed_criteria: crit })).toEqual(crit);
  });
});

describe('higher level with evidence', () => {
  test('shown only when the highest supported level is above the assigned one', () => {
    expect(hasHigherEvidence({ assessed_level: 'JUNIOR', highest_supported_level: 'SENIOR' })).toBe(true);
    expect(hasHigherEvidence({ assessed_level: 'UNKNOWN', highest_supported_level: 'MIDDLE' })).toBe(true);
    expect(hasHigherEvidence({ assessed_level: 'SENIOR', highest_supported_level: 'SENIOR' })).toBe(false);
    expect(hasHigherEvidence({ assessed_level: 'UNKNOWN', highest_supported_level: 'UNKNOWN' })).toBe(false);
    expect(higherEvidenceText({ assessed_level: 'MIDDLE', highest_supported_level: 'MIDDLE' })).toBeNull();
    expect(higherEvidenceText({ assessed_level: 'JUNIOR', highest_supported_level: 'SENIOR' })).toBe(
      'Є докази й для вищого рівня (Senior), але нижчий рівень підтверджено не повністю, тому вищий рівень не присвоюється.');
  });

  test('the server line about the higher level is not repeated next to the dedicated block', () => {
    const base = { note: null, explanation: ['Підтверджено Junior за перевіреними критеріями.',
      'Критерії Senior підтверджено, але нижчі рівні не підтверджені, тому цей рівень не присвоюється.'] };
    expect(explanationWithoutHigher({ ...base, assessed_level: 'JUNIOR', highest_supported_level: 'SENIOR' }))
      .toEqual(['Підтверджено Junior за перевіреними критеріями.']);
    expect(explanationWithoutHigher({ ...base, assessed_level: 'SENIOR', highest_supported_level: 'SENIOR' }))
      .toEqual(base.explanation);
  });
});

describe('higherNotice (audit I-4)', () => {
  const cov = (status: 'SUPPORTED' | 'GAP' | 'UNVERIFIED', extra: Record<string, unknown> = {}) => ({
    status, critical_total: 9, assessed_count: 0, confirmed_count: 0, gap_count: 0, confirmed: [], gaps: [],
    unassessed: [], ...extra,
  });

  test('a hard gap below the highest level blocks the achievement block and names the gap', () => {
    const level = {
      assessed_level: 'UNKNOWN' as const, highest_supported_level: 'SENIOR' as const,
      coverage_by_level: {
        JUNIOR: cov('GAP', { gaps: [{ id: 'python-core.idioms', title: 'Ідіоматичний код', kind: 'COMPETENCY' as const }],
          hard_gaps: [{ id: 'python-core.idioms', title: 'Ідіоматичний код', kind: 'COMPETENCY' as const }] }),
        MIDDLE: cov('SUPPORTED'), SENIOR: cov('SUPPORTED'),
      },
    };
    const n = higherNotice(level);
    expect(n?.kind).toBe('blocked');
    expect(n?.level).toBe('JUNIOR');
    expect(n?.text).toBe('Увага: на рівні Junior виявлено критичні прогалини: «Ідіоматичний код». '
      + 'Тому вищий рівень не присвоюється, навіть якщо окремі відповіді йому відповідають.');
  });

  test('missing lower evidence (no gap) keeps the higher-evidence block', () => {
    const n = higherNotice({ assessed_level: 'JUNIOR', highest_supported_level: 'SENIOR',
      coverage_by_level: { JUNIOR: cov('SUPPORTED'), MIDDLE: cov('UNVERIFIED'), SENIOR: cov('SUPPORTED') } });
    expect(n).toEqual({ kind: 'evidence', level: 'SENIOR',
      text: 'Є докази й для вищого рівня (Senior), але нижчий рівень підтверджено не повністю, тому вищий рівень не присвоюється.' });
    expect(higherNotice({ assessed_level: 'MIDDLE', highest_supported_level: 'MIDDLE', coverage_by_level: {} })).toBeNull();
  });
});
