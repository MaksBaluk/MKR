/** Pure helpers for the results page: URL filter state, pagination and fit labels. No ranking happens here. */
import type { CompetencyResult } from '@/types';

export interface ResultsFilters {
  work_mode: string;
  seniority: string;
  q: string;
  /** Minimum «Збіг профілю» in percent; one of MIN_SHARE_OPTIONS. */
  min_share: number;
  page: number;
}

export const DEFAULT_FILTERS: ResultsFilters = { work_mode: '', seniority: '', q: '', min_share: 0, page: 1 };

export const WORK_MODES = [
  { value: 'REMOTE', label: 'Віддалено' },
  { value: 'HYBRID', label: 'Гібрид' },
  { value: 'OFFICE', label: 'Офіс' },
] as const;

export const SENIORITIES = [
  { value: 'JUNIOR', label: 'Junior' },
  { value: 'MIDDLE', label: 'Middle' },
  { value: 'SENIOR', label: 'Senior' },
  { value: 'LEAD', label: 'Lead' },
] as const;

export const MIN_SHARE_OPTIONS = [0, 25, 50, 75] as const;

export const PAGE_SIZE = 10;

function pick(value: string | null, allowed: readonly { value: string }[]): string {
  const v = (value ?? '').toUpperCase();
  return allowed.some((a) => a.value === v) ? v : '';
}

export function filtersFromQuery(sp: URLSearchParams): ResultsFilters {
  const share = Number(sp.get('min_share'));
  const page = Number(sp.get('page'));
  return {
    work_mode: pick(sp.get('work_mode'), WORK_MODES),
    seniority: pick(sp.get('seniority'), SENIORITIES),
    q: (sp.get('q') ?? '').trim().slice(0, 120),
    min_share: (MIN_SHARE_OPTIONS as readonly number[]).includes(share) ? share : 0,
    page: Number.isInteger(page) && page >= 1 ? page : 1,
  };
}

/** URL state for the browser address bar: defaults are omitted to keep links short. */
export function filtersToQuery(f: ResultsFilters): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.work_mode) sp.set('work_mode', f.work_mode);
  if (f.seniority) sp.set('seniority', f.seniority);
  if (f.q.trim()) sp.set('q', f.q.trim());
  if (f.min_share) sp.set('min_share', String(f.min_share));
  if (f.page > 1) sp.set('page', String(f.page));
  return sp;
}

/** One list of every vacancy of the cohort, ordered by the server (highest match first). */
export function resultsApiPath(profileId: string, f: ResultsFilters, pageSize: number): string {
  const sp = new URLSearchParams({ page: String(f.page), page_size: String(pageSize), fitting: 'all' });
  if (f.work_mode) sp.set('work_mode', f.work_mode);
  if (f.seniority) sp.set('seniority', f.seniority);
  if (f.q.trim()) sp.set('q', f.q.trim());
  if (f.min_share) sp.set('min_share', String(f.min_share));
  return `/profiles/${encodeURIComponent(profileId)}/results?${sp.toString()}`;
}

export function hasActiveFilters(f: ResultsFilters): boolean {
  return Boolean(f.work_mode || f.seniority || f.q.trim() || f.min_share);
}

export function totalPages(total: number, pageSize: number): number {
  return Math.ceil(total / pageSize);
}

/** Page buttons: first, last, current ±1; runs of hidden pages become a single 'gap'. */
export function pageRange(page: number, pages: number): (number | 'gap')[] {
  const keep = new Set([1, pages, page - 1, page, page + 1]);
  const out: (number | 'gap')[] = [];
  for (let p = 1; p <= pages; p++) {
    if (keep.has(p) || pages <= 5) out.push(p);
    else if (out[out.length - 1] !== 'gap') out.push('gap');
  }
  return out;
}

export function fitLabel(share: number): string {
  return `Збіг профілю ${share}%`;
}

/** «із N вимоги» for 1, 21, 31… (not 11); «із N вимог» otherwise. */
export function assessedLabel(assessed: number, total: number): string {
  const word = total % 10 === 1 && total % 100 !== 11 ? 'вимоги' : 'вимог';
  return `оцінено ${assessed} із ${total} ${word}`;
}

export const FIT_EXPLANATION =
  'Розраховано за вашими відповідями в співбесіді. Невідомі вимоги вважаються нульовими, тому значення зростає з кількістю відповідей. Це не ймовірність працевлаштування.';

/** «Знайдено 1 вакансію / 3 вакансії / 5 вакансій». */
export function vacancyCount(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  const word = m10 === 1 && m100 !== 11 ? 'вакансію' : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? 'вакансії' : 'вакансій';
  return `Знайдено ${n} ${word}`;
}

/** Interview score (read-only LLM) and self-rating side by side, in server order; nulls stay null. */
export function comparisonRows(competencies: Pick<CompetencyResult, 'action_name' | 'interview_score' | 'self_rating'>[]) {
  return competencies.map((c) => ({ name: c.action_name, interview: c.interview_score, self: c.self_rating }));
}
