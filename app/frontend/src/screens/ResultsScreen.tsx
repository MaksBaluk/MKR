import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Loader2, MapPin, MessageSquare, Search, SearchX } from 'lucide-react';
import { api, ApiError } from '@/api';
import { InfoPopover } from '@/components/InfoPopover';
import { Pagination } from '@/components/Pagination';
import { ScaleLegend } from '@/components/ScaleLegend';
import { SourceMark } from '@/components/SourceMark';
import { FitChips } from '@/components/VacancyFit';
import { ErrorRetry } from '@/components/ErrorRetry';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Input, Select } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { FIT_ANCHOR } from '@/lib/vacancyFit';
import { bandFor } from '@/lib/bands';
import {
  assessedLabel, DEFAULT_FILTERS, FIT_EXPLANATION, filtersFromQuery, filtersToQuery, fitLabel,
  hasActiveFilters, MIN_SHARE_OPTIONS, PAGE_SIZE, resultsApiPath, SENIORITIES, totalPages, vacancyCount,
  WORK_MODES, type ResultsFilters,
} from '@/lib/results';
import { useStartAttempt } from '@/hooks/useStartAttempt';
import type { CandidateProfile, CompetencyResult, ProfileResults, ResultVacancy, SelfRatingValue } from '@/types';

const errorText = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback);

const WORK_MODE_LABEL: Record<string, string> = Object.fromEntries(WORK_MODES.map((m) => [m.value, m.label]));
const SENIORITY_LABEL: Record<string, string> = Object.fromEntries(SENIORITIES.map((m) => [m.value, m.label]));

/** Profile self-ratings (the chart's thin marker and the editable list). */
export function useSelfRatings(profileId: string) {
  const [items, setItems] = useState<SelfRatingValue[] | null>(null);
  const reload = useCallback(async () => {
    try {
      const r = await api<{ items: SelfRatingValue[] }>(`/profiles/${encodeURIComponent(profileId)}/self-ratings`);
      setItems(r.items);
    } catch {
      setItems((cur) => cur ?? []);
    }
  }, [profileId]);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { items, reload };
}

/** Shown when the active profile has no finished attempt yet. Starts or resumes one. */
export function NoResultsState({ profile }: { profile: CandidateProfile }) {
  const { start, pendingId, error } = useStartAttempt();
  const busy = pendingId === profile.id;
  return (
    <EmptyState icon={MessageSquare} title="Результатів для цього профілю ще немає"
      action={
        <Button onClick={() => void start(profile.id)} disabled={pendingId !== null}>
          {busy && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
          Пройти співбесіду
        </Button>
      }>
      <p>Профіль «{profile.name}» ще не має завершеної співбесіди. Після неї тут з’являться вакансії, упорядковані за вашими відповідями.</p>
      {error && <Alert role="alert" variant="danger" className="mt-3 text-left">{error.message}</Alert>}
    </EmptyState>
  );
}

function FitBlock({ item }: { item: ResultVacancy }) {
  if (item.label === 'NOT_EVALUABLE')
    return <Badge>Немає вимог для оцінки</Badge>;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-start justify-between gap-2">
        <p className="flex flex-col">
          <span className="text-xs text-ink-subtle">Збіг профілю</span>
          <span className="text-2xl font-bold tabular-nums text-primary">{item.confirmed_share}%</span>
        </p>
        <InfoPopover label="Як розраховано збіг профілю">{FIT_EXPLANATION}</InfoPopover>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-muted" role="img" aria-label={fitLabel(item.confirmed_share)}>
        <div className="h-full rounded-full bg-primary transition-[width] duration-500 motion-reduce:transition-none"
          style={{ width: `${item.confirmed_share}%` }} />
      </div>
      <p className="text-xs text-ink-subtle">{assessedLabel(item.groups_assessed, item.groups_total)}</p>
      {item.label === 'LOW_INFORMATION' && <Badge className="self-start">Мало даних</Badge>}
    </div>
  );
}

function VacancyCard({ item, rank }: { item: ResultVacancy; rank: number }) {
  const href = `/vacancies/${encodeURIComponent(item.vacancy_id)}`;
  const meta = [item.work_mode && WORK_MODE_LABEL[item.work_mode], item.seniority && SENIORITY_LABEL[item.seniority]]
    .filter(Boolean) as string[];
  return (
    <Card className="flex flex-col gap-4 p-4 sm:flex-row sm:p-5">
      <div className="flex min-w-0 flex-1 gap-3 sm:gap-4">
        <div className="flex shrink-0 flex-col items-center gap-2">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary-soft text-sm font-semibold tabular-nums text-primary"
            aria-label={`Місце ${rank}`}>{rank}</span>
          <SourceMark label={item.source_label} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold text-ink [overflow-wrap:anywhere]">
            <Link to={href} className="rounded hover:text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              {item.title}
            </Link>
          </h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-ink-muted">
            <span>{item.company}</span>
            {item.location && (
              <>
                <span aria-hidden="true" className="text-line-strong">·</span>
                <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" aria-hidden="true" />{item.location}</span>
              </>
            )}
            {meta.map((m) => (
              <span key={m} className="inline-flex items-center gap-2"><span aria-hidden="true" className="text-line-strong">·</span>{m}</span>
            ))}
          </p>
          {item.tags.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Ключові навички">
              {item.tags.map((t) => <li key={t}><Badge variant="info">{t}</Badge></li>)}
            </ul>
          )}
          <div className="mt-3 flex flex-col gap-2">
            <FitChips summary={{ met: item.met_count, gap: item.gap_count, unknown: item.unknown_count }} />
            {item.gaps.length > 0 && (
              <p className="text-sm text-ink-muted"><span className="font-medium text-ink">Головні прогалини: </span>{item.gaps.slice(0, 2).join('; ')}</p>
            )}
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-3 border-t border-line pt-3 sm:w-56 sm:shrink-0 sm:border-t-0 sm:border-l sm:pt-0 sm:pl-5">
        <FitBlock item={item} />
        <Button asChild size="sm">
          <Link to={`${href}#${FIT_ANCHOR}`} aria-label={`Де я підходжу: «${item.title}»`}>Де я підходжу</Link>
        </Button>
        <Button asChild variant="outline" size="sm">
          <Link to={href} aria-label={`Деталі вакансії «${item.title}»`}>Деталі</Link>
        </Button>
      </div>
    </Card>
  );
}

function CompetencySection({ competencies }: { competencies: CompetencyResult[] }) {
  const [showAll, setShowAll] = useState(false);
  const scored = competencies.filter((c) => c.score !== null).sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const visible = showAll ? scored : scored.slice(0, 5);
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>Ваші компетентності за співбесідою</CardTitle>
        <CardDescription>Оцінку робить автоматичний оцінювач за вашими відповідями. Змінювати можна лише власну самооцінку.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {scored.length === 0 ? (
          <p className="text-sm text-ink-muted">
            Оцінок поки немає: у відповідях замало свідчень або автоматичний оцінювач не встиг їх опрацювати.
          </p>
        ) : (
          <ul className="flex flex-col gap-4">
            {visible.map((c) => {
              const score = c.score ?? 0;
              const band = bandFor(score);
              const pct = Math.round(score * 100);
              return (
                <li key={c.action_id} className="flex flex-col gap-1.5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-sm font-semibold text-ink">{c.action_name}</span>
                    <Badge variant={band.badge}>{band.label}</Badge>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-surface-muted" role="img"
                    aria-label={`${c.action_name}: ${band.label} рівень, ${pct} з 100`} title={`${pct} з 100`}>
                    <div className={`h-full rounded-full ${band.bar}`} style={{ width: `${pct}%` }} />
                  </div>
                  {c.reason && <p className="text-sm text-ink-muted">{c.reason}</p>}
                </li>
              );
            })}
          </ul>
        )}
        {scored.length > 5 && (
          <Button variant="ghost" size="sm" className="self-start" aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>
            {showAll ? 'Показати лише перші 5' : `Показати всі (${scored.length})`}
          </Button>
        )}
        <ScaleLegend />
      </CardContent>
    </Card>
  );
}

function FilterBar({ filters, onChange }: { filters: ResultsFilters; onChange: (f: ResultsFilters) => void }) {
  const [q, setQ] = useState(filters.q);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  // The debounced search must merge into the filters current when it fires, not when the key was pressed.
  const latest = useRef(filters);
  latest.current = filters;
  useEffect(() => setQ(filters.q), [filters.q]);
  useEffect(() => () => clearTimeout(timer.current), []);

  function typeQ(value: string) {
    setQ(value);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => onChange({ ...latest.current, q: value, page: 1 }), 350);
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    clearTimeout(timer.current);
    onChange({ ...filters, q, page: 1 });
  }
  const set = (patch: Partial<ResultsFilters>) => onChange({ ...filters, ...patch, page: 1 });

  return (
    <form role="search" aria-label="Фільтри вакансій" onSubmit={submit}
      className="grid gap-3 sm:grid-cols-3">
      <div className="flex flex-col gap-1.5 sm:col-span-3">
        <Label htmlFor="f-q">Пошук</Label>
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-subtle" aria-hidden="true" />
          <Input id="f-q" type="search" value={q} onChange={(e) => typeQ(e.target.value)} className="pl-9"
            placeholder="Посада або компанія" maxLength={120} />
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="f-mode">Формат роботи</Label>
        <Select id="f-mode" value={filters.work_mode} onChange={(e) => set({ work_mode: e.target.value })}>
          <option value="">Будь-який</option>
          {WORK_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="f-sen">Рівень посади</Label>
        <Select id="f-sen" value={filters.seniority} onChange={(e) => set({ seniority: e.target.value })}>
          <option value="">Будь-який</option>
          {SENIORITIES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="f-share">Збіг профілю від</Label>
        <Select id="f-share" value={String(filters.min_share)} onChange={(e) => set({ min_share: Number(e.target.value) })}>
          {MIN_SHARE_OPTIONS.map((v) => <option key={v} value={v}>{v === 0 ? 'Будь-який' : `Від ${v}%`}</option>)}
        </Select>
      </div>
    </form>
  );
}

export function ResultsScreen({ profile }: { profile: CandidateProfile }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = filtersFromQuery(searchParams);
  const apiPath = resultsApiPath(profile.id, filters, PAGE_SIZE);
  const [data, setData] = useState<ProfileResults | null>(null);
  const [cohortTotal, setCohortTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const listHeading = useRef<HTMLHeadingElement>(null);
  const filtered = hasActiveFilters(filters);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    api<ProfileResults>(apiPath)
      .then((r) => {
        if (!live) return;
        setData(r);
        if (!filtered) setCohortTotal(r.total);
      })
      .catch((err) => live && setError(errorText(err, 'Не вдалося завантажити результати. Спробуйте ще раз.')))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [apiPath, filtered, nonce]);

  // Cohort size for the stat tile when the page was opened with filters already in the URL.
  useEffect(() => {
    if (!filtered || cohortTotal !== null) return;
    let live = true;
    api<ProfileResults>(resultsApiPath(profile.id, DEFAULT_FILTERS, 1))
      .then((r) => live && setCohortTotal(r.total))
      .catch(() => null);
    return () => {
      live = false;
    };
  }, [filtered, cohortTotal, profile.id]);

  const update = (f: ResultsFilters) => setSearchParams(filtersToQuery(f));
  const goPage = (p: number) => {
    update({ ...filters, page: p });
    listHeading.current?.focus();
    listHeading.current?.scrollIntoView({ block: 'start' });
  };

  if (!data && loading)
    return (
      <div className="flex flex-col gap-4" aria-busy="true">
        <p role="status" className="sr-only">Завантаження результатів…</p>
        <Skeleton className="h-24" />
        <div className="grid gap-4 xl:grid-cols-2"><Skeleton className="h-72" /><Skeleton className="h-72" /></div>
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-40" />)}
      </div>
    );

  if (!data)
    return (
      <ErrorRetry message={error} onRetry={() => setNonce((n) => n + 1)} />
    );

  if (!data.has_results) return <NoResultsState profile={profile} />;

  const pages = totalPages(data.total, PAGE_SIZE);
  const offset = (data.page - 1) * data.page_size;

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
      <section aria-labelledby="vacancies-title" className="flex flex-col gap-4">
        <h2 id="vacancies-title" ref={listHeading} tabIndex={-1} className="scroll-mt-24 text-xl font-semibold tracking-tight text-ink">
          Вакансії вашої добірки
        </h2>
        <Card className="p-4 sm:p-5"><FilterBar filters={filters} onChange={update} /></Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-ink-muted" role="status" aria-live="polite">
            {loading ? 'Оновлюємо список…' : `${vacancyCount(data.total)}${pages > 1 ? ` · сторінка ${data.page} із ${pages}` : ''}`}
          </p>
          {filtered && (
            <Button variant="ghost" size="sm" onClick={() => update(DEFAULT_FILTERS)}>Скинути фільтри</Button>
          )}
        </div>
        {error && (
          <ErrorRetry message={error} onRetry={() => setNonce((n) => n + 1)} />
        )}
        {data.items.length === 0 && !loading ? (
          <EmptyState icon={SearchX} headingLevel={3} title="Немає вакансій за цими фільтрами"
            action={filtered
              ? <Button variant="outline" onClick={() => update(DEFAULT_FILTERS)}>Скинути фільтри</Button>
              : <Button variant="outline" onClick={() => update({ ...filters, page: 1 })}>До першої сторінки</Button>}>
            Змініть умови пошуку або поверніться до повного списку.
          </EmptyState>
        ) : (
          <ol className={`flex flex-col gap-3 transition-opacity motion-reduce:transition-none ${loading ? 'opacity-60' : ''}`}
            aria-busy={loading} aria-label="Вакансії за порядком релевантності">
            {data.items.map((item, i) => (
              <li key={item.vacancy_id}><VacancyCard item={item} rank={offset + i + 1} /></li>
            ))}
          </ol>
        )}
        <Pagination page={data.page} pages={pages} onPage={goPage} />
      </section>
      <aside className="flex min-w-0 flex-col gap-4 xl:sticky xl:top-24">
        <CompetencySection competencies={data.competencies} />
      </aside>
    </div>
  );
}

