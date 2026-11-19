import type { AssessedLevel, LevelName, LevelPool, ResultSection } from '@/types';

const LEVEL_LABEL: Record<LevelName, string> = {
  JUNIOR: 'Junior', MIDDLE: 'Middle', SENIOR: 'Senior', UNKNOWN: 'Недостатньо даних',
};
const DESIRED_LABEL: Record<string, string> = { junior: 'Junior', middle: 'Middle', senior: 'Senior', lead: 'Lead' };

export function levelLabel(l: LevelName): string {
  return LEVEL_LABEL[l] ?? LEVEL_LABEL.UNKNOWN;
}

/** Desired level as stored on the profile (lower case) or null. */
export function desiredLabel(v: string | null): string {
  return (v && DESIRED_LABEL[v.toLowerCase()]) || 'Не вказано';
}

/** Display order of the sections. */
export const SECTIONS: readonly ResultSection[] = ['DESIRED_LEVEL', 'OTHER_FITTING', 'UNRESOLVED_OR_GAPS'];

const SECTION_TITLE: Record<ResultSection, string> = {
  DESIRED_LEVEL: 'Вакансії бажаного рівня',
  OTHER_FITTING: 'Інші вакансії, що підходять за підтвердженими вимогами',
  UNRESOLVED_OR_GAPS: 'Вакансії з невирішеними або невиконаними критичними вимогами',
};

export function sectionTitle(s: ResultSection): string {
  return SECTION_TITLE[s];
}

/**
 * Groups the given items (the current results page only: the server paginates the percent-first list, so a section
 * may continue on the next page) under their server section. Never drops an item: a missing or unknown section falls
 * into UNRESOLVED_OR_GAPS. Keeps the input order inside each section; empty sections are omitted; keys follow SECTIONS.
 */
export function groupBySection<T extends { section?: ResultSection }>(items: readonly T[]): Partial<Record<ResultSection, T[]>> {
  const buckets = new Map<ResultSection, T[]>(SECTIONS.map((s) => [s, []]));
  for (const item of items) {
    const key = item.section && buckets.has(item.section) ? item.section : 'UNRESOLVED_OR_GAPS';
    buckets.get(key)!.push(item);
  }
  const out: Partial<Record<ResultSection, T[]>> = {};
  for (const s of SECTIONS) if (buckets.get(s)!.length) out[s] = buckets.get(s);
  return out;
}

const POLICY_LINE = /^Політика рівнів \S+ є робочим припущенням/;

/** Explanation lines for display. The server's policy line names the internal policy id; when the separate policy
 * note is shown it replaces that line. */
export function explanationLines(level: Pick<AssessedLevel, 'explanation' | 'note'>): string[] {
  return level.note ? level.explanation.filter((l) => !POLICY_LINE.test(l)) : level.explanation;
}

/** What was not checked: whole capabilities for a pooled policy (v2), otherwise the critical criteria (v1 rows). */
export function unassessedItems(level: Pick<AssessedLevel, 'unassessed_criteria' | 'unassessed_pools'>): LevelPool[] {
  return level.unassessed_pools?.length ? level.unassessed_pools : level.unassessed_criteria;
}
