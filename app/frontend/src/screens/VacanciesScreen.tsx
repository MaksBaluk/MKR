import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { MapPin, Search, SearchX, SlidersHorizontal } from 'lucide-react';
import { api, ApiError } from '@/api';
import { ErrorRetry } from '@/components/ErrorRetry';
import { Pagination } from '@/components/Pagination';
import { SourceMark } from '@/components/SourceMark';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Input, Select } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { TRACKS, trackLabel } from '@/lib/profiles';
import { SENIORITIES, totalPages, vacancyCount, WORK_MODES } from '@/lib/results';
import { cn } from '@/lib/utils';
import {
  DEFAULT_VACANCY_FILTERS, SALARY_OPTIONS, SENIORITY_LABEL, WORK_MODE_LABEL, VACANCY_PAGE_SIZE, VACANCY_SORTS, formatSalary, hasVacancyFilters,
  stackPreview, vacanciesApiPath, vacancyFiltersFromQuery, vacancyFiltersToQuery, type VacancyFilters, type VacancySort,
} from '@/lib/vacancies';
import type { CatalogPage, CatalogVacancy } from '@/types';


type TextKey = 'q' | 'location';

function VacancyRow({ v, fromList }: { v: CatalogVacancy; fromList: string }) {
  const href = `/vacancies/${encodeURIComponent(v.id)}`;
  const salary = formatSalary(v.salary_min, v.salary_max, v.currency);
  const { shown, rest } = stackPreview(v.stack);
  return (
    <Card className="flex gap-3 p-4 transition-colors hover:border-primary-line sm:gap-4 sm:p-5">
      <SourceMark label={v.source_label} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <h2 className="min-w-0 text-base font-semibold text-ink [overflow-wrap:anywhere]">
            <Link to={href} state={{ fromList }}
              className="rounded hover:text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              {v.title}
            </Link>
          </h2>
          {salary && (
            <p className="shrink-0 text-sm font-semibold whitespace-nowrap text-success-ink">
              <span className="sr-only">Зарплата: </span>{salary}
            </p>
          )}
        </div>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-ink-muted">
          <span className="font-medium text-ink">{v.company}</span>
          {v.location && (
            <span className="inline-flex items-center gap-1">
              <span aria-hidden="true" className="text-line-strong">·</span>
              <MapPin className="size-3.5" aria-hidden="true" />{v.location}
            </span>
          )}
          {v.work_mode && WORK_MODE_LABEL[v.work_mode] && (
            <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="text-line-strong">·</span>{WORK_MODE_LABEL[v.work_mode]}</span>
          )}
          <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="text-line-strong">·</span>{trackLabel(v.track)}</span>
        </p>
        {v.summary && <p className="mt-2 line-clamp-2 text-sm text-ink-muted">{v.summary}</p>}
        <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Рівень і технології">
          {v.seniority && SENIORITY_LABEL[v.seniority] && <li><Badge variant="warning">{SENIORITY_LABEL[v.seniority]}</Badge></li>}
          {shown.map((t) => <li key={t}><Badge variant="info">{t}</Badge></li>)}
          {rest > 0 && <li><Badge><span aria-hidden="true">+{rest}</span><span className="sr-only">і ще {rest}</span></Badge></li>}
        </ul>
      </div>
    </Card>
  );
}

function FacetSelect({ id, label, value, options, counts, onChange }: {
  id: string;
  label: string;
  value: string;
  options: readonly { value: string; label: string }[];
  counts: Record<string, number> | undefined;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Усі</option>
        {options.map((o) => {
          const n = counts?.[o.value] ?? 0;
          return (
            <option key={o.value} value={o.value} disabled={n === 0 && o.value !== value}>
              {counts ? `${o.label} (${n})` : o.label}
            </option>
          );
        })}
      </Select>
    </div>
  );
}

export function VacanciesScreen() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { search } = useLocation();
  const filters = vacancyFiltersFromQuery(searchParams);
  const apiPath = vacanciesApiPath(filters, VACANCY_PAGE_SIZE);
  const [data, setData] = useState<CatalogPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [showFilters, setShowFilters] = useState(false);
  const [text, setText] = useState({ q: filters.q, location: filters.location });
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  // Debounced text must merge into the filters current when it fires (a select may have changed meanwhile).
  const latest = useRef(filters);
  latest.current = filters;
  const listHeading = useRef<HTMLHeadingElement>(null);
  const ids = { q: useId(), loc: useId(), track: useId(), mode: useId(), sen: useId(), sal: useId(), sort: useId(), panel: useId() };
  const filtered = hasVacancyFilters(filters);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    api<CatalogPage>(apiPath)
      .then((r) => live && setData(r))
      .catch((err) => live && setError(err instanceof ApiError ? err.message : 'Не вдалося завантажити вакансії. Спробуйте ще раз.'))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [apiPath, nonce]);

  // Back/forward or «Скинути фільтри» change the URL: mirror it into the text inputs.
  useEffect(() => setText({ q: filters.q, location: filters.location }), [filters.q, filters.location]);
  useEffect(() => () => clearTimeout(timer.current), []);

  /** Filter changes replace the history entry so Back does not replay every keystroke; pages push. */
  const update = (f: VacancyFilters, push = false) => setSearchParams(vacancyFiltersToQuery(f), { replace: !push });
  const set = (patch: Partial<VacancyFilters>) => {
    clearTimeout(timer.current);
    update({ ...latest.current, ...text, ...patch, page: 1 });
  };
  function type(key: TextKey, value: string) {
    setText((t) => ({ ...t, [key]: value }));
    clearTimeout(timer.current);
    timer.current = setTimeout(() => update({ ...latest.current, [key]: value, page: 1 }), 400);
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    set({});
  }
  function reset() {
    clearTimeout(timer.current);
    update({ ...DEFAULT_VACANCY_FILTERS, sort: filters.sort });
  }
  const goPage = (p: number) => {
    update({ ...filters, page: p }, true);
    listHeading.current?.focus();
    listHeading.current?.scrollIntoView({ block: 'start' });
  };

  const pages = data ? totalPages(data.total, data.page_size) : 0;
  const activeCount = [filters.track, filters.work_mode, filters.seniority, filters.location, filters.salary_min, filters.q]
    .filter(Boolean).length;

  return (
    <div className="flex flex-col gap-4">
      <form role="search" aria-label="Пошук вакансій" onSubmit={submit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <Label htmlFor={ids.q}>Пошук</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-subtle" aria-hidden="true" />
            <Input id={ids.q} type="search" value={text.q} onChange={(e) => type('q', e.target.value)} className="pl-9"
              placeholder="Посада, компанія або технологія" maxLength={120} />
          </div>
        </div>
        <div className="flex gap-2">
          <Button type="submit" className="flex-1 sm:flex-none">Знайти</Button>
          <Button type="button" variant="outline" className="lg:hidden" aria-expanded={showFilters} aria-controls={ids.panel}
            onClick={() => setShowFilters((v) => !v)}>
            <SlidersHorizontal className="size-4" aria-hidden="true" />
            Фільтри{activeCount > 0 && <span className="tabular-nums"> ({activeCount})</span>}
          </Button>
        </div>
      </form>

      <div className="grid items-start gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <Card id={ids.panel} className={cn('flex-col gap-4 p-4 lg:sticky lg:top-20 lg:flex', showFilters ? 'flex' : 'hidden')}>
          <h2 className="text-sm font-semibold text-ink">Фільтри</h2>
          <FacetSelect id={ids.track} label="Напрям" value={filters.track} options={TRACKS} counts={data?.facets.track}
            onChange={(v) => set({ track: v })} />
          <FacetSelect id={ids.mode} label="Формат роботи" value={filters.work_mode} options={WORK_MODES} counts={data?.facets.work_mode}
            onChange={(v) => set({ work_mode: v })} />
          <FacetSelect id={ids.sen} label="Рівень посади" value={filters.seniority} options={SENIORITIES} counts={data?.facets.seniority}
            onChange={(v) => set({ seniority: v })} />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={ids.loc}>Місто</Label>
            <Input id={ids.loc} value={text.location} onChange={(e) => type('location', e.target.value)}
              placeholder="Наприклад, Lviv" maxLength={80} autoComplete="off" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={ids.sal}>Зарплата від</Label>
            <Select id={ids.sal} value={String(filters.salary_min)} onChange={(e) => set({ salary_min: Number(e.target.value) })}
              aria-describedby={`${ids.sal}-hint`}>
              <option value="0">Будь-яка</option>
              {SALARY_OPTIONS.map((s) => <option key={s} value={s}>від {s}</option>)}
            </Select>
            <p id={`${ids.sal}-hint`} className="text-xs text-ink-subtle">У валюті вакансії (USD або EUR) на місяць.</p>
          </div>
          {filtered && <Button variant="ghost" size="sm" onClick={reset}>Скинути фільтри</Button>}
        </Card>

        <section aria-labelledby="vacancy-list-title" className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="vacancy-list-title" ref={listHeading} tabIndex={-1} className="scroll-mt-24 text-lg font-semibold tracking-tight text-ink">
                Каталог вакансій
              </h2>
              <p className="text-sm text-ink-muted" role="status" aria-live="polite">
                {loading ? 'Завантажуємо вакансії…' : data ? `${vacancyCount(data.total)}${pages > 1 ? ` · сторінка ${data.page} із ${pages}` : ''}` : ''}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Label htmlFor={ids.sort} className="whitespace-nowrap">Сортування</Label>
              <Select id={ids.sort} value={filters.sort} onChange={(e) => update({ ...filters, sort: e.target.value as VacancySort, page: 1 })}>
                {VACANCY_SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </Select>
            </div>
          </div>

          {error && <ErrorRetry message={error} onRetry={() => setNonce((n) => n + 1)} />}

          {!data && loading ? (
            <div className="flex flex-col gap-3" aria-busy="true">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-36" />)}
            </div>
          ) : data && data.items.length === 0 && !loading ? (
            <EmptyState icon={SearchX} title="Вакансій не знайдено"
              action={filtered
                ? <Button variant="outline" onClick={reset}>Скинути фільтри</Button>
                : <Button variant="outline" onClick={() => update({ ...filters, page: 1 })}>До першої сторінки</Button>}>
              Змініть умови пошуку або поверніться до повного списку.
            </EmptyState>
          ) : data ? (
            <ul className={cn('flex flex-col gap-3 transition-opacity motion-reduce:transition-none', loading && 'opacity-60')}
              aria-busy={loading} aria-label="Вакансії">
              {data.items.map((v) => <li key={v.id}><VacancyRow v={v} fromList={`/vacancies${search}`} /></li>)}
            </ul>
          ) : null}

          {data && <Pagination page={data.page} pages={pages} onPage={goPage} label="Сторінки каталогу" />}
        </section>
      </div>
    </div>
  );
}
