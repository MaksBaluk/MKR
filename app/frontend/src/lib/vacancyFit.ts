import type { FitAlternative, FitGroup, FitGroupStatus, FitState, VacancyFitBreakdown } from '@/types';

export const pct = (v: number | null): number | null => (v === null ? null : Math.round(v * 100));

/** Profile match shown to the user: never 100, because the score is an assessment of answers, not a certainty. */
export const shareLabel = (percent: number): number => Math.min(99, Math.round(percent));

/** The weakest required criterion of an alternative with the count of the other weak ones, or null. */
function weakest(a: FitAlternative): { title: string; score: number; more: number } | null {
  const list = a.weak_criteria ?? [];
  if (list.length === 0) return null;
  const w = list.reduce((m, c) => (c.score < m.score ? c : m));
  return { title: w.title, score: w.score, more: list.length - 1 };
}
const moreText = (n: number) => (n > 0 ? ` і ще ${n}` : '');

const STATE_TAIL: Record<Exclude<FitState, 'UNKNOWN'>, string> = {
  MET: 'достатньо', BORDERLINE: 'майже достатньо', GAP: 'не вистачає',
};

/** «Потрібен робочий рівень, у вас 45%: не вистачає». */
export function altText(a: FitAlternative): string {
  const need = `Потрібен ${a.required_label} рівень`;
  if (a.candidate_score === null) return `${need}, не оцінювали`;
  if (a.state === 'UNKNOWN') return `${need}, оцінено лише частину критеріїв`;
  const w = a.state === 'GAP' ? weakest(a) : null;
  if (w) return `${need}: у середньому ${pct(a.candidate_score)}%, але «${w.title}» лише ${pct(w.score)}%${moreText(w.more)}`;
  return `${need}, у вас ${pct(a.candidate_score)}%: ${STATE_TAIL[a.state]}`;
}

export const groupStatusText = (s: FitGroupStatus): string =>
  s === 'SATISFIED' ? 'Підходить' : s === 'FAILED' ? 'Не підходить' : 'Невідомо';

export type ChipTone = 'success' | 'warning' | 'default';
export function summaryChips(s: VacancyFitBreakdown['summary']): { key: 'met' | 'gap' | 'unknown'; text: string; tone: ChipTone }[] {
  return [
    { key: 'met', text: `Підходить: ${s.met}`, tone: 'success' },
    { key: 'gap', text: `Прогалини: ${s.gap}`, tone: 'warning' },
    { key: 'unknown', text: `Не оцінено: ${s.unknown}`, tone: 'default' },
  ];
}

const UNKNOWN_WHY = 'Це не оцінювали у співбесіді, тому невідомо, чи ви відповідаєте.';

/** One-sentence reason for a gap or unknown group; null when the group is satisfied. */
export function whySentence(g: FitGroup): string | null {
  if (g.status === 'SATISFIED') return null;
  if (g.status === 'UNRESOLVED') return UNKNOWN_WHY;
  const scored = g.alternatives.filter((a) => a.candidate_score !== null);
  if (scored.length === 0) return UNKNOWN_WHY;
  if (g.alternatives.length === 1) {
    const a = scored[0];
    const w = weakest(a);
    if (w) {
      return `Не вистачає: «${w.title}»${moreText(w.more)} — ${pct(w.score)}%, потрібно від ${pct(a.threshold)}% за кожним критерієм. `
        + `У середньому за темою ${pct(a.candidate_score)}%.`;
    }
    return `Не вистачає: ${a.name}. Потрібно від ${pct(a.threshold)}%, у вас ${pct(a.candidate_score)}%.`;
  }
  const best = scored.reduce((m, a) => ((a.candidate_score ?? 0) > (m.candidate_score ?? 0) ? a : m));
  return `Жоден з варіантів не досягає потрібного рівня. Найближче: ${best.name} (${pct(best.candidate_score)}%).`;
}

/** Mandatory groups first, then desired; stable inside each kind. */
export const orderGroups = (groups: FitGroup[]): FitGroup[] =>
  [...groups.filter((g) => g.kind === 'MANDATORY'), ...groups.filter((g) => g.kind !== 'MANDATORY')];

export const FIT_ANCHOR = 'fit';
