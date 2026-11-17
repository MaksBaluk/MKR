import type { FitAlternative, FitGroup, FitGroupStatus, FitState, VacancyFitBreakdown } from '@/types';

export const pct = (v: number | null): number | null => (v === null ? null : Math.round(v * 100));

const STATE_TAIL: Record<Exclude<FitState, 'UNKNOWN'>, string> = {
  MET: 'достатньо', BORDERLINE: 'майже достатньо', GAP: 'не вистачає',
};

/** «Потрібен робочий рівень, у вас 45%: не вистачає». */
export function altText(a: FitAlternative): string {
  const need = `Потрібен ${a.required_label} рівень`;
  if (a.candidate_score === null) return `${need}, не оцінювали`;
  if (a.state === 'UNKNOWN') return `${need}, оцінено лише частину критеріїв`;
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
    return `Не вистачає: ${a.name}. Потрібно від ${pct(a.threshold)}%, у вас ${pct(a.candidate_score)}%.`;
  }
  const best = scored.reduce((m, a) => ((a.candidate_score ?? 0) > (m.candidate_score ?? 0) ? a : m));
  return `Жоден з варіантів не досягає потрібного рівня. Найближче: ${best.name} (${pct(best.candidate_score)}%).`;
}

/** Mandatory groups first, then desired; stable inside each kind. */
export const orderGroups = (groups: FitGroup[]): FitGroup[] =>
  [...groups.filter((g) => g.kind === 'MANDATORY'), ...groups.filter((g) => g.kind !== 'MANDATORY')];

export const FIT_ANCHOR = 'fit';
