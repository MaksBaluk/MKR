import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, ChevronDown, HelpCircle, Lightbulb, ListChecks, MessageSquareQuote, Sparkles, Target, Trophy, type LucideIcon } from 'lucide-react';
import { api } from '@/api';
import { InfoPopover } from '@/components/InfoPopover';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { confirmedTopics, fitSections, groupTitle, levelBadge, pickQuotes, recommendation } from '@/lib/fitView';
import { FIT_EXPLANATION } from '@/lib/results';
import { FIT_ANCHOR, shareLabel, whySentence } from '@/lib/vacancyFit';
import type { CompetencyResult, FitGroup, ProfileResults, VacancyFitBreakdown } from '@/types';

/** Ring with the profile match. A match of answers to requirements, never a probability of being hired. */
export function FitRing({ percent }: { percent: number }) {
  const value = shareLabel(percent);
  const r = 44;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative size-28 shrink-0" role="img" aria-label={`Збіг профілю: ${value} відсотків`}>
      <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden="true">
        <circle cx="50" cy="50" r={r} fill="none" strokeWidth="9" className="stroke-primary-soft" />
        <circle cx="50" cy="50" r={r} fill="none" strokeWidth="9" strokeLinecap="round" className="stroke-primary"
          strokeDasharray={`${(c * value) / 100} ${c}`} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center" aria-hidden="true">
        <span className="text-2xl font-bold tabular-nums text-ink">{value}%</span>
        <span className="text-xs text-ink-muted">збіг</span>
      </div>
    </div>
  );
}

const TONE = {
  met: { box: 'bg-success-soft text-success-ink', icon: CheckCircle2 },
  gap: { box: 'bg-warning-soft text-warning-ink', icon: AlertTriangle },
  unknown: { box: 'bg-surface-muted text-ink-muted', icon: HelpCircle },
} as const;

function Section({ tone, title, groups, hint, children }: {
  tone: keyof typeof TONE; title: string; groups: FitGroup[]; hint?: string; children: (g: FitGroup) => ReactNode;
}) {
  if (groups.length === 0) return null;
  const t = TONE[tone];
  return (
    <details open className="group rounded-xl border border-line">
      <summary className={`flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring ${t.box}`}>
        <t.icon className="size-4 shrink-0" aria-hidden="true" />
        <span className="flex-1">{title} ({groups.length})</span>
        <ChevronDown className="size-4 transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
      </summary>
      {hint && <p className="px-3 pt-2 text-sm text-ink-muted">{hint}</p>}
      <ul className="flex flex-col divide-y divide-line px-3">{groups.map((g) => <li key={g.id} className="py-2.5">{children(g)}</li>)}</ul>
    </details>
  );
}

function Row({ g, tone, note }: { g: FitGroup; tone: keyof typeof TONE; note: string | null }) {
  const Icon = TONE[tone].icon;
  const level = levelBadge(g);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-start gap-2">
        <Icon className={`mt-0.5 size-4 shrink-0 ${tone === 'met' ? 'text-success' : tone === 'gap' ? 'text-warning' : 'text-ink-subtle'}`} aria-hidden="true" />
        <span className="min-w-0 flex-1 text-sm font-medium text-ink [overflow-wrap:anywhere]">{groupTitle(g)}</span>
        {level && <Badge variant="info" className="shrink-0">{level}</Badge>}
      </div>
      <p className="pl-6 text-xs text-ink-subtle">{g.kind === 'MANDATORY' ? 'Обов’язкова вимога' : 'Бажана вимога'}</p>
      {note && <p className="pl-6 text-sm text-ink-muted">{note}</p>}
    </div>
  );
}

function Panel({ icon: Icon, title, className = '', children }: { icon: LucideIcon; title: string; className?: string; children: ReactNode }) {
  return (
    <Card className={`flex flex-col gap-3 p-4 sm:p-5 ${className}`}>
      <h3 className="flex items-center gap-2 text-base font-semibold text-ink"><Icon className="size-5 text-primary" aria-hidden="true" />{title}</h3>
      {children}
    </Card>
  );
}

/** The candidate's results list once: own interview quotes and the neighbouring vacancy for «Наступна вакансія». */
export function useResultsContext(profileId: string, vacancyId: string) {
  const [competencies, setCompetencies] = useState<CompetencyResult[]>([]);
  const [nextId, setNextId] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api<ProfileResults>(`/profiles/${encodeURIComponent(profileId)}/results?page_size=50`)
      .then((r) => {
        if (!live) return;
        setCompetencies(r.competencies);
        const i = r.items.findIndex((x) => x.vacancy_id === vacancyId);
        setNextId(i >= 0 && i + 1 < r.items.length ? r.items[i + 1].vacancy_id : null);
      })
      .catch(() => live && (setCompetencies([]), setNextId(null)));  // the extras are optional; the explanation itself stays
    return () => { live = false; };
  }, [profileId, vacancyId]);
  return { competencies, nextId };
}

/** «Де ви підходите і чому»: requirements by outcome, grounds of the grade, strengths and growth areas. */
export function FitExplanation({ data, profileId }: { data: VacancyFitBreakdown; profileId: string }) {
  const { competencies, nextId } = useResultsContext(profileId, data.vacancy_id);
  const s = fitSections(data.groups);
  const quotes = pickQuotes(data.groups, competencies);
  const topics = confirmedTopics(data.groups);
  const open = [...s.gap, ...s.unknown];
  return (
    <section id={FIT_ANCHOR} className="scroll-mt-24 flex flex-col gap-4" aria-labelledby="fit-title">
      <div className="flex items-center gap-2">
        <h2 id="fit-title" className="text-lg font-semibold text-ink">Де ви підходите і чому</h2>
        <InfoPopover label="Як розраховано збіг профілю">{FIT_EXPLANATION}</InfoPopover>
      </div>
      <p className="-mt-2 text-sm text-ink-muted">
        Збіг профілю — це не ймовірність отримати роботу. Оцінка стосується ваших відповідей у співбесіді, а не перевіреного досвіду.
      </p>
      {data.groups.length === 0 && <p className="text-sm text-ink-muted">Для цієї вакансії немає вимог для оцінки.</p>}
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Panel icon={ListChecks} title="Вимоги вакансії">
          <Section tone="met" title="Відповідають" groups={s.met}>{(g) => <Row g={g} tone="met" note={null} />}</Section>
          <Section tone="gap" title="Прогалини" groups={s.gap}>{(g) => <Row g={g} tone="gap" note={whySentence(g)} />}</Section>
          <Section tone="unknown" title="Не оцінено" groups={s.unknown} hint="Цього не оцінювали у співбесіді, тому невідомо, чи ви відповідаєте.">
            {(g) => <Row g={g} tone="unknown" note={null} />}
          </Section>
        </Panel>
        <Panel icon={MessageSquareQuote} title="Підстави оцінювання">
          <div className="flex flex-col gap-2 rounded-xl bg-primary-soft/50 p-3">
            <h4 className="text-sm font-semibold text-ink">Відповіді з інтерв’ю</h4>
            {quotes.length === 0
              ? <p className="text-sm text-ink-muted">Для цієї вакансії немає збережених цитат із ваших відповідей.</p>
              : quotes.map((q) => (
                <figure key={q.name} className="flex flex-col gap-1">
                  <blockquote className="text-sm text-ink [overflow-wrap:anywhere]">«{q.text}»</blockquote>
                  <figcaption className="text-xs text-ink-subtle">Тема: {q.name}</figcaption>
                </figure>
              ))}
          </div>
          <div className="flex flex-col gap-2 rounded-xl bg-surface-muted p-3">
            <h4 className="flex items-center gap-1.5 text-sm font-semibold text-ink"><Sparkles className="size-4 text-primary" aria-hidden="true" />Підтверджені теми</h4>
            {topics.length === 0
              ? <p className="text-sm text-ink-muted">Поки жодну тему цієї вакансії не підтверджено.</p>
              : <ul className="flex flex-wrap gap-1.5">{topics.map((t) => <li key={t}><Badge variant="success">{t}</Badge></li>)}</ul>}
          </div>
          <div className="flex flex-col gap-1.5 rounded-xl bg-warning-soft/50 p-3">
            <h4 className="flex items-center gap-1.5 text-sm font-semibold text-ink"><Lightbulb className="size-4 text-warning" aria-hidden="true" />Рекомендації</h4>
            <p className="text-sm text-ink">{recommendation(s)}</p>
          </div>
        </Panel>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel icon={Trophy} title="Сильні сторони" className="bg-success-soft/40">
          {s.met.length === 0 ? <p className="text-sm text-ink-muted">Підтверджених вимог поки немає.</p> : (
            <ul className="flex flex-col gap-1.5">
              {s.met.map((g) => (
                <li key={g.id} className="flex items-start gap-2 text-sm text-ink">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />{groupTitle(g)}
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel icon={Target} title="Зони розвитку" className="bg-warning-soft/40">
          {open.length === 0 ? <p className="text-sm text-ink-muted">Прогалин і неоцінених вимог немає.</p> : (
            <ul className="flex flex-col gap-1.5">
              {open.map((g) => (
                <li key={g.id} className="flex items-start gap-2 text-sm text-ink">
                  <span className="mt-1.5 size-2.5 shrink-0 rounded-full border-2 border-warning" aria-hidden="true" />
                  <span>{groupTitle(g)} <span className="text-ink-subtle">· {g.status === 'FAILED' ? 'прогалина' : 'не оцінено'}</span></span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <nav aria-label="Навігація вакансіями" className="flex flex-wrap items-center justify-between gap-3">
        <Button asChild variant="outline"><Link to="/results"><ArrowLeft className="size-4" aria-hidden="true" />Повернутися до рейтингу</Link></Button>
        {nextId && <Button asChild><Link to={`/vacancies/${encodeURIComponent(nextId)}#fit`}>Наступна вакансія<ArrowRight className="size-4" aria-hidden="true" /></Link></Button>}
      </nav>
    </section>
  );
}
