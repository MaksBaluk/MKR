import { describe, expect, test } from 'vitest';
import { altText, groupStatusText, pct, shareLabel, summaryChips, whySentence } from '@/lib/vacancyFit';
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
  test('shareLabel never shows 100', () => {
    expect(shareLabel(100)).toBe(99);
    expect(shareLabel(99.6)).toBe(99);
    expect(shareLabel(87.4)).toBe(87);
    expect(shareLabel(0)).toBe(0);
  });
  test('a gap with a high average names the weak criterion', () => {
    const a = alt({ candidate_score: 0.8, threshold: 0.75, weak_criteria: [{ id: 'x.a', title: 'Валідація запитів', score: 0.55 }] });
    expect(altText(a)).toBe('Потрібен робочий рівень: у середньому 80%, але «Валідація запитів» лише 55%');
    expect(whySentence(group({ alternatives: [a] })))
      .toBe('Не вистачає: «Валідація запитів» — 55%, потрібно від 75% за кожним критерієм. У середньому за темою 80%.');
  });
  test('several weak criteria show the weakest and a count', () => {
    const a = alt({ candidate_score: 0.8, threshold: 0.75, weak_criteria: [
      { id: 'x.a', title: 'Перший', score: 0.6 }, { id: 'x.b', title: 'Другий', score: 0.4 }] });
    expect(altText(a)).toBe('Потрібен робочий рівень: у середньому 80%, але «Другий» лише 40% і ще 1');
  });
});
