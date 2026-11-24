import { describe, expect, test } from 'vitest';
import { clip, confirmedTopics, fitSections, groupTitle, levelBadge, pickQuotes, recommendation } from '@/lib/fitView';
import type { CompetencyResult, FitAlternative, FitGroup } from '@/types';

const alt = (o: Partial<FitAlternative> = {}): FitAlternative => ({
  competency_id: 'py', name: 'Python', required_level: 3, required_label: 'просунутий', threshold: 0.75,
  candidate_score: 0.9, state: 'MET', ...o,
});
const group = (o: Partial<FitGroup> = {}): FitGroup => ({
  id: 'g', kind: 'MANDATORY', label: 'Python', excerpt: '', status: 'SATISFIED', alternatives: [alt()], ...o,
});
const comp = (o: Partial<CompetencyResult> = {}): CompetencyResult => ({
  action_id: 'py', action_name: 'Python', score: 0.9, interview_score: 0.9, self_rating: null, reason: '',
  sufficient_evidence: true, evidence: [{ turn_id: 't', exact_excerpt: 'Я оптимізував запити.' }], ...o,
});

describe('fitView', () => {
  test('sections split by status, mandatory first', () => {
    const s = fitSections([group({ id: 'a', kind: 'DESIRED' }), group({ id: 'b', status: 'FAILED' }),
      group({ id: 'c', status: 'UNRESOLVED' }), group({ id: 'd' })]);
    expect(s.met.map((g) => g.id)).toEqual(['d', 'a']);
    expect(s.gap.map((g) => g.id)).toEqual(['b']);
    expect(s.unknown.map((g) => g.id)).toEqual(['c']);
  });
  test('group title falls back to alternative names', () => {
    expect(groupTitle(group({ label: ' ', alternatives: [alt({ name: 'React' }), alt({ name: 'Vue' })] }))).toBe('React або Vue');
    expect(groupTitle(group())).toBe('Python');
  });
  test('level badge uses the lowest required level among alternatives', () => {
    expect(levelBadge(group({ alternatives: [alt(), alt({ required_level: 1, required_label: 'базовий' })] }))).toBe('базовий рівень');
    expect(levelBadge(group({ alternatives: [] }))).toBeNull();
  });
  test('clip shortens and collapses whitespace', () => {
    expect(clip('a  b\n c')).toBe('a b c');
    expect(clip('x'.repeat(300), 10)).toHaveLength(10);
    expect(clip('x'.repeat(300), 10).endsWith('…')).toBe(true);
  });
  test('quotes only for topics of the vacancy, best score first, no empty evidence', () => {
    const q = pickQuotes([group(), group({ alternatives: [alt({ competency_id: 'sql', name: 'SQL' })] })], [
      comp({ action_id: 'sql', action_name: 'SQL', interview_score: 0.95, evidence: [{ turn_id: 't', exact_excerpt: 'Писав міграції.' }] }),
      comp(), comp({ action_id: 'other', action_name: 'Інше' }), comp({ action_id: 'py', evidence: [] }),
    ], 2);
    expect(q.map((x) => x.name)).toEqual(['SQL', 'Python']);
    expect(pickQuotes([group()], [], 2)).toEqual([]);
    const same = comp({ action_id: 'sql', action_name: 'SQL' });
    expect(pickQuotes([group(), group({ alternatives: [alt({ competency_id: 'sql' })] })], [comp(), same], 2)).toHaveLength(1);
  });
  test('confirmed topics are unique met alternatives', () => {
    expect(confirmedTopics([group(), group(), group({ alternatives: [alt({ name: 'Kafka', state: 'GAP' })] })])).toEqual(['Python']);
  });
  test('recommendation names open topics and promises nothing', () => {
    const open = recommendation(fitSections([group({ status: 'FAILED', label: 'Docker' }), group({ status: 'UNRESOLVED', label: 'AWS' })]));
    expect(open).toContain('Docker, AWS');
    expect(open).not.toMatch(/%|підвищить|гарант/);
    expect(recommendation(fitSections([group()]))).toContain('підтверджено');
  });
});
