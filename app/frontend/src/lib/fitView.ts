import type { FitAlternative, FitGroup, CompetencyResult } from '@/types';

export interface FitSections { met: FitGroup[]; gap: FitGroup[]; unknown: FitGroup[] }

/** Requirement groups by outcome; mandatory first inside each part, order otherwise unchanged. */
export function fitSections(groups: FitGroup[]): FitSections {
  const ordered = [...groups.filter((g) => g.kind === 'MANDATORY'), ...groups.filter((g) => g.kind !== 'MANDATORY')];
  return {
    met: ordered.filter((g) => g.status === 'SATISFIED'),
    gap: ordered.filter((g) => g.status === 'FAILED'),
    unknown: ordered.filter((g) => g.status === 'UNRESOLVED'),
  };
}

/** «Python» or «React або Vue»: the group label, else its alternatives' names. */
export const groupTitle = (g: FitGroup): string => g.label.trim() || g.alternatives.map((a) => a.name).join(' або ');

/** «просунутий рівень»; with alternatives, the lowest required level, because one alternative is enough. */
export function levelBadge(g: FitGroup): string | null {
  if (g.alternatives.length === 0) return null;
  const lowest = g.alternatives.reduce((m: FitAlternative, a) => (a.required_level < m.required_level ? a : m));
  return `${lowest.required_label} рівень`;
}

export function clip(text: string, max = 220): string {
  const t = text.replace(/\s+/g, ' ').trim();
  return t.length <= max ? t : `${t.slice(0, max - 1).trimEnd()}…`;
}

/** Candidate's own words behind the topics this vacancy asks about: best graded topics first, at most `max` quotes. */
export function pickQuotes(groups: FitGroup[], competencies: CompetencyResult[], max = 2): { name: string; text: string }[] {
  const wanted = new Set(groups.flatMap((g) => g.alternatives.map((a) => a.competency_id)));
  return competencies
    .filter((c) => wanted.has(c.action_id) && c.evidence.length > 0 && c.evidence[0].exact_excerpt.trim() !== '')
    .sort((a, b) => (b.interview_score ?? -1) - (a.interview_score ?? -1))
    .map((c) => ({ name: c.action_name, text: clip(c.evidence[0].exact_excerpt) }))
    .filter((q, i, all) => all.findIndex((x) => x.text === q.text) === i)  // the same answer can back several topics
    .slice(0, max);
}

/** Names of the topics the vacancy confirmed through the candidate's answers (graded alternatives that were met). */
export function confirmedTopics(groups: FitGroup[]): string[] {
  const out: string[] = [];
  for (const g of groups) for (const a of g.alternatives) if (a.state === 'MET' && !out.includes(a.name)) out.push(a.name);
  return out;
}

/** Plain next step. It never promises a score change: more concrete answers only give the evaluator more to grade. */
export function recommendation(s: FitSections): string {
  const open = [...s.gap, ...s.unknown].map(groupTitle);
  if (open.length === 0) return 'Усі вимоги цієї вакансії підтверджено вашими відповідями в співбесіді.';
  const names = open.slice(0, 3).join(', ');
  return `Щоб оцінка стала повнішою, у наступній співбесіді наведіть конкретні приклади зі своєї практики за темами: ${names}.`;
}
