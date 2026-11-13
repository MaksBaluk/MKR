/** Pure helpers for the vacancy catalogue (list URL state, labels) and the vacancy detail page (description parsing). */
import { SENIORITIES, WORK_MODES } from '@/lib/results';
import { TRACKS } from '@/lib/profiles';

export const WORK_MODE_LABEL: Record<string, string> = Object.fromEntries(WORK_MODES.map((m) => [m.value, m.label]));
export const SENIORITY_LABEL: Record<string, string> = Object.fromEntries(SENIORITIES.map((m) => [m.value, m.label]));

export const VACANCY_SORTS = [
  { value: 'title', label: 'За назвою' },
  { value: 'newest', label: 'Спочатку нові' },
  { value: 'salary_desc', label: 'Зарплата: від більшої' },
  { value: 'salary_asc', label: 'Зарплата: від меншої' },
] as const;

export type VacancySort = (typeof VACANCY_SORTS)[number]['value'];

/** «Зарплата від» options; compared with the upper bound of the vacancy's range in its own currency. */
export const SALARY_OPTIONS = [1000, 2000, 3000, 4000, 5000] as const;

export const VACANCY_PAGE_SIZE = 20;

export interface VacancyFilters {
  track: string;
  work_mode: string;
  seniority: string;
  location: string;
  salary_min: number;
  q: string;
  sort: VacancySort;
  page: number;
}

export const DEFAULT_VACANCY_FILTERS: VacancyFilters = {
  track: '', work_mode: '', seniority: '', location: '', salary_min: 0, q: '', sort: 'title', page: 1,
};

function pickEnum(value: string | null, allowed: readonly { value: string }[]): string {
  const v = (value ?? '').trim().toLowerCase();
  return allowed.find((a) => a.value.toLowerCase() === v)?.value ?? '';
}

export function vacancyFiltersFromQuery(sp: URLSearchParams): VacancyFilters {
  const salary = Number(sp.get('salary_min'));
  const page = Number(sp.get('page'));
  return {
    track: pickEnum(sp.get('track'), TRACKS),
    work_mode: pickEnum(sp.get('work_mode'), WORK_MODES),
    seniority: pickEnum(sp.get('seniority'), SENIORITIES),
    location: (sp.get('location') ?? '').trim().slice(0, 80),
    salary_min: (SALARY_OPTIONS as readonly number[]).includes(salary) ? salary : 0,
    q: (sp.get('q') ?? '').trim().slice(0, 120),
    sort: (pickEnum(sp.get('sort'), VACANCY_SORTS) || 'title') as VacancySort,
    page: Number.isInteger(page) && page >= 1 ? page : 1,
  };
}

/** Address-bar state: defaults are omitted to keep links short. */
export function vacancyFiltersToQuery(f: VacancyFilters): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.q.trim()) sp.set('q', f.q.trim());
  if (f.track) sp.set('track', f.track);
  if (f.work_mode) sp.set('work_mode', f.work_mode);
  if (f.seniority) sp.set('seniority', f.seniority);
  if (f.location.trim()) sp.set('location', f.location.trim());
  if (f.salary_min) sp.set('salary_min', String(f.salary_min));
  if (f.sort !== 'title') sp.set('sort', f.sort);
  if (f.page > 1) sp.set('page', String(f.page));
  return sp;
}

export function vacanciesApiPath(f: VacancyFilters, pageSize: number): string {
  const sp = new URLSearchParams({ page: String(f.page), page_size: String(pageSize), sort: f.sort });
  for (const [k, v] of vacancyFiltersToQuery({ ...f, sort: 'title', page: 1 })) sp.set(k, v);
  return `/vacancies?${sp.toString()}`;
}

export function hasVacancyFilters(f: VacancyFilters): boolean {
  return Boolean(f.track || f.work_mode || f.seniority || f.location.trim() || f.salary_min || f.q.trim());
}

/** Required competency level 1..3 in words; the only place these words are defined. */
const LEVEL_WORDS: Record<number, string> = { 1: 'Базовий', 2: 'Середній', 3: 'Просунутий' };

export function levelWord(level: number): string {
  return LEVEL_WORDS[level] ?? `Рівень ${level}`;
}

const KIND_LABELS: Record<string, string> = { MANDATORY: 'Обов’язкова', DESIRED: 'Бажана' };

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}

const EMPLOYMENT_LABELS: Record<string, string> = {
  'Full-time': 'Повна зайнятість', 'Part-time': 'Часткова зайнятість', Contract: 'Контракт',
};

export function employmentLabel(value: string | null): string | null {
  if (!value) return null;
  return EMPLOYMENT_LABELS[value] ?? value;
}

/** Nominative plural after a count: 1 рік, 2 роки, 5 років. */
function yearsNom(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'рік';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'роки';
  return 'років';
}

/** Genitive after «від»/«до»: від 1 року, від 2 років. */
function yearsGen(n: number): string {
  return n % 10 === 1 && n % 100 !== 11 ? 'року' : 'років';
}

/** «1 рік», «3 роки», «5 років». */
export function yearsCount(n: number): string {
  return `${n} ${yearsNom(n)}`;
}

export function yearsLabel(min: number | null, max: number | null): string | null {
  const lo = min && min > 0 ? min : null;
  if (lo !== null && max !== null && max > 0) return `${lo}–${max} ${yearsNom(max)}`;
  if (lo !== null) return `від ${lo} ${yearsGen(lo)}`;
  if (max !== null && max > 0) return `до ${max} ${yearsGen(max)}`;
  return null;
}

function groupDigits(n: number): string {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

export function formatSalary(min: number | null, max: number | null, currency: string | null): string | null {
  const cur = currency ? ` ${currency}` : '';
  if (min !== null && max !== null) return min === max ? `${groupDigits(min)}${cur}` : `${groupDigits(min)}–${groupDigits(max)}${cur}`;
  if (min !== null) return `від ${groupDigits(min)}${cur}`;
  if (max !== null) return `до ${groupDigits(max)}${cur}`;
  return null;
}

export function stackPreview(stack: readonly string[] | null, limit = 5): { shown: string[]; rest: number } {
  const all = stack ?? [];
  return { shown: all.slice(0, limit), rest: Math.max(0, all.length - limit) };
}

export type DescriptionNode =
  | { type: 'heading'; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; items: string[] };

const BULLET = /^[-•*]\s+/;

/**
 * Turns the plain-text vacancy description into headings, paragraphs and bullet lists.
 * Blocks are separated by blank lines; a short first line without a final full stop is the block heading.
 * The output is text only: callers render it as React text nodes, never as HTML.
 */
export function parseDescription(text: string | null | undefined, title: string): DescriptionNode[] {
  const blocks = (text ?? '').replace(/\r\n?/g, '\n').split(/\n\s*\n/)
    .map((b) => b.split('\n').map((l) => l.trim()).filter(Boolean))
    .filter((b) => b.length > 0);
  const out: DescriptionNode[] = [];
  blocks.forEach((lines, i) => {
    if (i === 0 && lines.length === 1 && title && lines[0].startsWith(title)) return;
    let rest = lines;
    const first = lines[0];
    if (lines.length > 1 && !BULLET.test(first) && first.length <= 80 && !/[.!?;:]$/.test(first)) {
      out.push({ type: 'heading', text: first });
      rest = lines.slice(1);
    }
    for (const line of rest) {
      if (BULLET.test(line)) {
        const item = line.replace(BULLET, '');
        const last = out[out.length - 1];
        if (last?.type === 'list') last.items.push(item);
        else out.push({ type: 'list', items: [item] });
      } else out.push({ type: 'paragraph', text: line });
    }
  });
  return out;
}

/** Items (responsibilities, benefits) that the description text does not already show. */
export function missingFromDescription(description: string | null, items: readonly string[] | null): string[] {
  const text = description ?? '';
  return (items ?? []).filter((item) => !text.includes(item));
}

/** «← До вакансій» target: the list URL the user came from (with its filters), else the plain list. */
export function backToListPath(state: unknown): string {
  const from = (state as { fromList?: unknown } | null)?.fromList;
  if (typeof from === 'string' && (from === '/vacancies' || from.startsWith('/vacancies?'))) return from;
  return '/vacancies';
}
