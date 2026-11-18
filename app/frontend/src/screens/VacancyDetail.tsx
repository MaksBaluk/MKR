import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ArrowLeft, Briefcase, Clock, ExternalLink, Loader2, MapPin, MessageSquare, SearchX } from 'lucide-react';
import { api, ApiError } from '@/api';
import { ErrorRetry } from '@/components/ErrorRetry';
import { useVacancyFit, VacancyFit } from '@/components/VacancyFit';
import { SourceMark } from '@/components/SourceMark';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useStartAttempt } from '@/hooks/useStartAttempt';
import { useActiveProfile } from '@/lib/activeProfile';
import { trackLabel } from '@/lib/profiles';
import {
  SENIORITY_LABEL, WORK_MODE_LABEL, backToListPath, employmentLabel, formatSalary, kindLabel, levelWord, missingFromDescription, parseDescription, yearsLabel,
} from '@/lib/vacancies';
import type { RequirementGroup, VacancyDetail as Vacancy } from '@/types';

function Description({ text, title }: { text: string | null; title: string }) {
  const nodes = parseDescription(text, title);
  if (nodes.length === 0) return <p className="text-sm text-ink-muted">Опису немає.</p>;
  return (
    <div className="flex flex-col gap-3 text-sm leading-relaxed text-ink">
      {nodes.map((n, i) =>
        n.type === 'heading' ? <h3 key={i} className="mt-3 text-base font-semibold text-ink first:mt-0">{n.text}</h3>
        : n.type === 'list' ? (
          <ul key={i} className="flex list-disc flex-col gap-1.5 pl-5 marker:text-ink-subtle">
            {n.items.map((it, j) => <li key={j}>{it}</li>)}
          </ul>
        ) : <p key={i}>{n.text}</p>,
      )}
    </div>
  );
}

function ExtraList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm marker:text-ink-subtle">
        {items.map((it) => <li key={it}>{it}</li>)}
      </ul>
    </section>
  );
}

function Requirement({ g }: { g: RequirementGroup }) {
  const mandatory = g.kind === 'MANDATORY';
  return (
    <li className="flex flex-col gap-2 border-b border-line py-3 last:border-b-0">
      <Badge variant={mandatory ? 'danger' : 'default'} className="self-start">{kindLabel(g.kind)}</Badge>
      <ul className="flex flex-col gap-1.5">
        {g.alternatives.map((a, i) => (
          <li key={a.competency_id} className="flex flex-col gap-1.5">
            {i > 0 && <span className="text-xs font-semibold tracking-wide text-ink-subtle uppercase">або</span>}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium text-ink">{a.name}</span>
              <Badge variant="info">{levelWord(a.required_level)} рівень</Badge>
            </div>
          </li>
        ))}
      </ul>
    </li>
  );
}

/** «Де ви підходите і чому» for the active profile; a hint with a profile link when there is no finished attempt. */
function FitSection({ vacancyId }: { vacancyId: string }) {
  const { active } = useActiveProfile();
  const finished = active?.latest_finished_attempt ? active.id : null;
  const { data, state, retry } = useVacancyFit(finished, vacancyId);
  const { hash } = useLocation();
  // The section appears after the fetch, so the browser's own anchor jump has nothing to land on yet.
  useEffect(() => {
    if (hash === '#fit' && (data || state === 'missing')) document.getElementById('fit')?.scrollIntoView({ block: 'start' });
  }, [hash, data, state]);
  if (!finished)
    return (
      <Card id="fit" className="scroll-mt-24 p-4 text-sm text-ink-muted">
        Щоб побачити, де ви підходите до цієї вакансії, завершіть співбесіду у{' '}
        <Link to="/profile" className="font-medium text-primary hover:underline">своєму профілі</Link>.
      </Card>
    );
  if (state === 'loading' && !data) return <div id="fit" aria-busy="true"><Skeleton className="h-48" /></div>;
  if (state === 'error') return <div id="fit"><ErrorRetry message="Не вдалося завантажити розбір збігу." onRetry={retry} /></div>;
  if (state === 'missing')
    return <Card id="fit" className="p-4 text-sm text-ink-muted">Ця вакансія не входить до вашої добірки, тому розбору збігу для неї немає.</Card>;
  return data ? <VacancyFit data={data} /> : null;
}

/** Interview CTA when the active profile is in this vacancy's track and has no finished attempt yet. */
function FitCta({ track }: { track: string }) {
  const { active } = useActiveProfile();
  const { start, pendingId, error } = useStartAttempt();
  if (!active || active.track !== track || active.latest_finished_attempt_id) return null;
  return (
    <Card className="flex flex-col gap-3 p-4">
      <p className="flex items-start gap-2 text-sm text-ink-muted">
        <MessageSquare className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
        Збіг профілю «{active.name}» з вакансіями з’явиться після співбесіди.
      </p>
      <Button onClick={() => void start(active.id)} disabled={pendingId !== null}>
        {pendingId && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
        Пройти співбесіду, щоб побачити збіг
      </Button>
      {error && <Alert role="alert" variant="danger">{error.message}</Alert>}
    </Card>
  );
}

export function VacancyDetail() {
  const { id = '' } = useParams();
  const { state } = useLocation();
  const back = backToListPath(state);
  const [v, setV] = useState<Vacancy | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    setError(null);
    setV(null);
    api<Vacancy>(`/vacancies/${encodeURIComponent(id)}`)
      .then((r) => {
        if (!live) return;
        setV(r);
        document.title = `${r.title} · CompetenceMatch`;
      })
      .catch((err) => live && setError({
        status: err instanceof ApiError ? err.status : 0,
        message: err instanceof ApiError ? err.message : 'Не вдалося завантажити вакансію.',
      }));
    return () => {
      live = false;
    };
  }, [id, nonce]);

  const backLink = (
    <Link to={back} className="inline-flex min-h-11 items-center gap-1.5 self-start rounded-xl text-sm font-medium text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
      <ArrowLeft className="size-4" aria-hidden="true" />До вакансій
    </Link>
  );

  if (error?.status === 404)
    return (
      <div className="flex flex-col gap-3">
        {backLink}
        <EmptyState icon={SearchX} title="Вакансію не знайдено"
          action={<Button asChild><Link to="/vacancies">До каталогу вакансій</Link></Button>}>
          Можливо, її прибрали з каталогу або в посиланні є помилка.
        </EmptyState>
      </div>
    );
  if (error)
    return <div className="flex flex-col gap-3">{backLink}<ErrorRetry message={error.message} onRetry={() => setNonce((n) => n + 1)} /></div>;
  if (!v)
    return (
      <div className="flex flex-col gap-3" aria-busy="true">
        <p role="status" className="sr-only">Завантаження вакансії…</p>
        {backLink}
        <Skeleton className="h-32" />
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]"><Skeleton className="h-96" /><Skeleton className="h-72" /></div>
      </div>
    );

  const salary = formatSalary(v.salary_min, v.salary_max, v.currency);
  const years = yearsLabel(v.years_min, v.years_max);
  const chips = [
    v.location && { icon: MapPin, text: v.location },
    v.work_mode && WORK_MODE_LABEL[v.work_mode] && { icon: Briefcase, text: WORK_MODE_LABEL[v.work_mode] },
    employmentLabel(v.employment) && { icon: Clock, text: employmentLabel(v.employment)! },
  ].filter(Boolean) as { icon: typeof MapPin; text: string }[];
  const responsibilities = missingFromDescription(v.description, v.responsibilities);
  const benefits = missingFromDescription(v.description, v.benefits);
  const mandatory = v.requirements.filter((g) => g.kind === 'MANDATORY');
  const desired = v.requirements.filter((g) => g.kind !== 'MANDATORY');

  return (
    <article aria-labelledby="vacancy-title" className="flex flex-col gap-4">
      {backLink}
      <Card className="flex flex-col gap-4 p-4 sm:flex-row sm:items-start sm:p-6">
        <SourceMark label={v.source_label} example={v.source_example} />
        <div className="min-w-0 flex-1">
          <h2 id="vacancy-title" className="text-xl font-bold tracking-tight text-ink [overflow-wrap:anywhere] sm:text-2xl">{v.title}</h2>
          <p className="mt-1 text-sm font-medium text-ink-muted">{v.company} · {trackLabel(v.track)}</p>
          <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Умови">
            {chips.map((c) => (
              <li key={c.text}><Badge className="py-1"><c.icon className="size-3.5" aria-hidden="true" />{c.text}</Badge></li>
            ))}
            {v.seniority && SENIORITY_LABEL[v.seniority] && <li><Badge variant="warning" className="py-1">{SENIORITY_LABEL[v.seniority]}</Badge></li>}
            {years && <li><Badge className="py-1">Досвід: {years}</Badge></li>}
          </ul>
        </div>
        <div className="shrink-0 rounded-xl bg-success-soft px-4 py-3 sm:text-right">
          <p className="text-xs text-success-ink">Зарплата на місяць</p>
          <p className="text-lg font-bold whitespace-nowrap text-success-ink">{salary ?? 'Не вказано'}</p>
        </div>
      </Card>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex min-w-0 flex-col gap-4">
          <FitSection vacancyId={v.id} />
          <Card className="flex flex-col gap-5 p-4 sm:p-6">
            <Description text={v.description} title={v.title} />
            <ExtraList title="Обов’язки" items={responsibilities} />
            <ExtraList title="Ми пропонуємо" items={benefits} />
            {v.stack && v.stack.length > 0 && (
              <section className="flex flex-col gap-2">
                <h3 className="text-base font-semibold text-ink">Технології та інструменти</h3>
                <ul className="flex flex-wrap gap-1.5">{v.stack.map((t) => <li key={t}><Badge variant="info">{t}</Badge></li>)}</ul>
              </section>
            )}
          </Card>
          <Card className="flex flex-col gap-2 p-4 text-sm text-ink-muted">
            <p>
              Джерело: <span className="font-medium text-ink">{v.source_label ?? 'не вказано'}</span>
            </p>
            {v.source_url ? (
              <a href={v.source_url} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 self-start font-medium text-primary hover:underline">
                Відкрити на джерелі<ExternalLink className="size-3.5" aria-hidden="true" />
                <span className="sr-only">(відкриється в новій вкладці)</span>
              </a>
            ) : null}
          </Card>
        </div>

        <aside aria-labelledby="req-title" className="flex flex-col gap-4 lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto">
          <Card className="p-4">
            <h2 id="req-title" className="text-base font-semibold text-ink">Вимоги</h2>
            <p className="mt-0.5 text-xs text-ink-subtle">
              Обов’язкових: {mandatory.length} · бажаних: {desired.length}. «Або» означає, що достатньо одного з варіантів.
            </p>
            {v.requirements.length === 0 ? (
              <p className="mt-3 text-sm text-ink-muted">Вимоги для цієї вакансії не виділено.</p>
            ) : (
              <ul className="mt-1">{[...mandatory, ...desired].map((g) => <Requirement key={g.id} g={g} />)}</ul>
            )}
          </Card>
          <FitCta track={v.track} />
        </aside>
      </div>
    </article>
  );
}
