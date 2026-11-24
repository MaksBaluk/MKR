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

const SECTION_BADGE: Record<ResultSection, string> = {
  DESIRED_LEVEL: 'бажаний рівень',
  OTHER_FITTING: 'інші, що підходять',
  UNRESOLVED_OR_GAPS: 'є прогалини',
};

/** Short badge for a vacancy's server section. A missing or unknown section is shown as "є прогалини", never dropped. */
export function sectionBadge(s: ResultSection | undefined): string {
  return (s && SECTION_BADGE[s]) || SECTION_BADGE.UNRESOLVED_OR_GAPS;
}

const POLICY_LINE = /^Політика рівнів \S+ є робочим припущенням/;

/** Explanation lines for display. The server's policy line names the internal policy id; when the separate policy
 * note is shown it replaces that line. */
export function explanationLines(level: Pick<AssessedLevel, 'explanation' | 'note'>): string[] {
  return level.note ? level.explanation.filter((l) => !POLICY_LINE.test(l)) : level.explanation;
}

const RANK: Record<LevelName, number> = { UNKNOWN: -1, JUNIOR: 0, MIDDLE: 1, SENIOR: 2 };

/** True when a level above the assigned one has its own evidence but a lower level is not fully confirmed. */
export function hasHigherEvidence(level: Pick<AssessedLevel, 'assessed_level' | 'highest_supported_level'>): boolean {
  return RANK[level.highest_supported_level] > RANK[level.assessed_level];
}

export type HigherNotice =
  | { kind: 'evidence'; level: LevelName; text: string }
  | { kind: 'blocked'; level: LevelName; text: string };

const LOWER_ORDER: LevelName[] = ['JUNIOR', 'MIDDLE', 'SENIOR'];

/**
 * What to say about a level above the assigned one. When a lower level has a critical gap (status GAP), the higher
 * evidence is not an achievement: the notice names that gap instead of showing the higher level prominently.
 */
export function higherNotice(level: Pick<AssessedLevel, 'assessed_level' | 'highest_supported_level' | 'coverage_by_level'>): HigherNotice | null {
  if (!hasHigherEvidence(level)) return null;
  const top = RANK[level.highest_supported_level];
  const blocked = LOWER_ORDER.find((l) => RANK[l] < top && level.coverage_by_level?.[l]?.status === 'GAP');
  if (blocked) {
    const cov = level.coverage_by_level[blocked];
    const names = (cov.hard_gaps?.length ? cov.hard_gaps : cov.gaps).map((c) => `«${c.title || c.id}»`);
    const what = names.length ? `: ${names.join(', ')}` : '';
    return { kind: 'blocked', level: blocked, text: `Увага: на рівні ${levelLabel(blocked)} виявлено критичні прогалини${what}. `
      + 'Тому вищий рівень не присвоюється, навіть якщо окремі відповіді йому відповідають.' };
  }
  return { kind: 'evidence', level: level.highest_supported_level, text: higherEvidenceText(level)! };
}

/** Ukrainian sentence for hasHigherEvidence; null when there is nothing to add. */
export function higherEvidenceText(level: Pick<AssessedLevel, 'assessed_level' | 'highest_supported_level'>): string | null {
  if (!hasHigherEvidence(level)) return null;
  return `Є докази й для вищого рівня (${levelLabel(level.highest_supported_level)}), але нижчий рівень `
    + 'підтверджено не повністю, тому вищий рівень не присвоюється.';
}

const HIGHER_LINE = /^Критерії \S+ підтверджено, але нижчі рівні не підтверджені/;

/** Explanation lines without the server's "higher level" line when the dedicated block shows it instead. */
export function explanationWithoutHigher(level: Pick<AssessedLevel, 'explanation' | 'note' | 'assessed_level' | 'highest_supported_level'>): string[] {
  const lines = explanationLines(level);
  return hasHigherEvidence(level) ? lines.filter((l) => !HIGHER_LINE.test(l)) : lines;
}

/** What was not checked: whole capabilities for a pooled policy (v2-v4), otherwise the critical criteria (v1 rows). */
export function unassessedItems(level: Pick<AssessedLevel, 'unassessed_criteria' | 'unassessed_pools'>): LevelPool[] {
  return level.unassessed_pools?.length ? level.unassessed_pools : level.unassessed_criteria;
}
