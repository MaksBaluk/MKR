import { describe, expect, test } from 'vitest';
import { altText, groupStatusText, pct, summaryChips, whySentence } from '@/lib/vacancyFit';
import type { FitAlternative, FitGroup } from '@/types';

const alt = (o: Partial<FitAlternative> = {}): FitAlternative => ({
  competency_id: 'c', name: 'React', required_level: 2, required_label: 'робочий', threshold: 0.6,
  candidate_score: 0.45, state: 'GAP', ...o,
});
const group = (o: Partial<FitGroup> = {}): FitGroup => ({
  id: 'g', kind: 'MANDATORY', label: 'React', excerpt: '', status: 'FAILED', alternatives: [alt()], ...o,
});

describe('vacancyFit', () => {
  test('pct rounds and handles null', () => {
    expect(pct(0.456)).toBe(46);
    expect(pct(null)).toBeNull();
  });
  test('gap text', () => {
    expect(altText(alt())).toBe('Потрібен робочий рівень, у вас 45%: не вистачає');
  });
  test('met text', () => {
    expect(altText(alt({ candidate_score: 0.8, state: 'MET' }))).toBe('Потрібен робочий рівень, у вас 80%: достатньо');
  });
  test('borderline text', () => {
    expect(altText(alt({ candidate_score: 0.58, state: 'BORDERLINE' }))).toBe('Потрібен робочий рівень, у вас 58%: майже достатньо');
  });
  test('unknown score', () => {
    expect(altText(alt({ candidate_score: null, state: 'UNKNOWN' }))).toBe('Потрібен робочий рівень, не оцінювали');
  });
  test('partly graded topic is not called borderline', () => {
    expect(altText(alt({ candidate_score: 0.95, coverage: 0.2, state: 'UNKNOWN' })))
      .toBe('Потрібен робочий рівень, оцінено лише частину критеріїв');
  });
  test('group status text', () => {
    expect(groupStatusText('SATISFIED')).toBe('Підходить');
    expect(groupStatusText('FAILED')).toBe('Не підходить');
    expect(groupStatusText('UNRESOLVED')).toBe('Невідомо');
  });
  test('summary chips carry text and counts', () => {
    const chips = summaryChips({ met: 3, gap: 1, unknown: 2 });
    expect(chips.map((c) => c.text)).toEqual(['Підходить: 3', 'Прогалини: 1', 'Не оцінено: 2']);
  });
  test('why: satisfied has none', () => {
    expect(whySentence(group({ status: 'SATISFIED', alternatives: [alt({ state: 'MET', candidate_score: 0.9 })] }))).toBeNull();
  });
  test('why: single gap', () => {
    expect(whySentence(group())).toBe('Не вистачає: React. Потрібно від 60%, у вас 45%.');
  });
  test('why: OR group none reaches level names closest', () => {
    const g = group({ alternatives: [alt({ name: 'Vue', candidate_score: 0.3 }), alt({ name: 'Angular', candidate_score: 0.5 })] });
    expect(whySentence(g)).toBe('Жоден з варіантів не досягає потрібного рівня. Найближче: Angular (50%).');
  });
  test('why: unknown', () => {
    const g = group({ status: 'UNRESOLVED', alternatives: [alt({ candidate_score: null, state: 'UNKNOWN' })] });
    expect(whySentence(g)).toBe('Це не оцінювали у співбесіді, тому невідомо, чи ви відповідаєте.');
  });
  test('why: OR with one unknown alternative', () => {
    const g = group({ status: 'UNRESOLVED', alternatives: [alt({ candidate_score: 0.3 }), alt({ name: 'Vue', candidate_score: null, state: 'UNKNOWN' })] });
    expect(whySentence(g)).toBe('Це не оцінювали у співбесіді, тому невідомо, чи ви відповідаєте.');
  });
});
