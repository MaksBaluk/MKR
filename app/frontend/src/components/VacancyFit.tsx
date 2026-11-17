import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, HelpCircle, type LucideIcon } from 'lucide-react';
import { api, ApiError } from '@/api';
import { InfoPopover } from '@/components/InfoPopover';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { FIT_EXPLANATION } from '@/lib/results';
import { altText, FIT_ANCHOR, groupStatusText, orderGroups, pct, summaryChips, whySentence } from '@/lib/vacancyFit';
import { kindLabel } from '@/lib/vacancies';
import type { FitAlternative, FitGroup, FitGroupStatus, VacancyFitBreakdown } from '@/types';

const CHIP_ICON = { met: CheckCircle2, gap: AlertTriangle, unknown: HelpCircle } as const;
const STATUS: Record<FitGroupStatus, { icon: LucideIcon; variant: 'success' | 'warning' | 'default' }> = {
  SATISFIED: { icon: CheckCircle2, variant: 'success' },
  FAILED: { icon: AlertTriangle, variant: 'warning' },
  UNRESOLVED: { icon: HelpCircle, variant: 'default' },
};
const FILL = { MET: 'bg-success', BORDERLINE: 'bg-primary', GAP: 'bg-warning', UNKNOWN: 'bg-line-strong' } as const;

/** Compact chips: met / gaps / not assessed. Text and icon, never colour alone. */
export function FitChips({ summary }: { summary: VacancyFitBreakdown['summary'] }) {
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Підсумок за вимогами">
      {summaryChips(summary).map((c) => {
        const Icon = CHIP_ICON[c.key];
        return <li key={c.key}><Badge variant={c.tone} className="py-1"><Icon className="size-3.5" aria-hidden="true" />{c.text}</Badge></li>;
      })}
    </ul>
  );
}

/** Threshold marker on a 0-100 track versus the candidate's interview grade (fill). */
function MiniScale({ a }: { a: FitAlternative }) {
  const score = pct(a.candidate_score);
  const need = pct(a.threshold) ?? 0;
  return (
    <div className="relative h-2.5 rounded-full bg-surface-muted" role="img" aria-label={altText(a)}>
      {score !== null && <div className={`h-full rounded-full ${FILL[a.state]}`} style={{ width: `${score}%` }} />}
      <span className="absolute top-[-3px] h-4 w-0.5 rounded bg-ink" style={{ left: `calc(${need}% - 1px)` }} aria-hidden="true" />
    </div>
  );
}

function Alt({ a }: { a: FitAlternative }) {
  return (
    <li className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-ink [overflow-wrap:anywhere]">{a.name}</span>
      <MiniScale a={a} />
      <p className="text-sm text-ink-muted">{altText(a)}</p>
    </li>
  );
}

function Group({ g }: { g: FitGroup }) {
  const st = STATUS[g.status];
  const why = whySentence(g);
  const or = g.alternatives.length > 1;
  return (
    <li className="flex flex-col gap-2 border-b border-line py-3 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={g.kind === 'MANDATORY' ? 'danger' : 'default'}>{kindLabel(g.kind)}</Badge>
        <Badge variant={st.variant}><st.icon className="size-3.5" aria-hidden="true" />{groupStatusText(g.status)}</Badge>
      </div>
      <p className="text-sm font-semibold text-ink [overflow-wrap:anywhere]">{g.label}</p>
      {or && <p className="text-xs font-medium text-ink-subtle">Достатньо одного з:</p>}
      <ul className="flex flex-col gap-3">{g.alternatives.map((a) => <Alt key={a.competency_id} a={a} />)}</ul>
      {why && <p className="text-sm text-ink"><span className="font-semibold">Чому: </span>{why}</p>}
    </li>
  );
}

export function VacancyFit({ data }: { data: VacancyFitBreakdown }) {
  const groups = orderGroups(data.groups);
  return (
    <Card id={FIT_ANCHOR} className="scroll-mt-24 p-4 sm:p-5" aria-labelledby="fit-title">
      <div className="flex items-start justify-between gap-2">
        <h2 id="fit-title" className="text-base font-semibold text-ink">Де ви підходите і чому</h2>
        <InfoPopover label="Як розраховано збіг профілю">{FIT_EXPLANATION}</InfoPopover>
      </div>
      <div className="mt-3 flex flex-col gap-2">
        <FitChips summary={data.summary} />
        <p className="text-sm text-ink-muted">
          Збіг профілю: <span className="font-bold tabular-nums text-primary">{data.confirmed_share}%</span>. Це не ймовірність отримати роботу.
        </p>
        <p className="text-xs text-ink-subtle">Оцінка стосується ваших відповідей у співбесіді, а не перевіреного досвіду. Чорна риска на шкалі показує потрібний рівень.</p>
      </div>
      {groups.length === 0
        ? <p className="mt-3 text-sm text-ink-muted">Для цієї вакансії немає вимог для оцінки.</p>
        : <ul className="mt-2">{groups.map((g) => <Group key={g.id} g={g} />)}</ul>}
    </Card>
  );
}

/** Loads the per-vacancy breakdown; `error` is set on 404 (no finished attempt or vacancy outside the cohort). */
export function useVacancyFit(profileId: string | null, vacancyId: string) {
  const [data, setData] = useState<VacancyFitBreakdown | null>(null);
  const [state, setState] = useState<'idle' | 'loading' | 'error' | 'missing'>('idle');
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    if (!profileId) { setData(null); setState('idle'); return; }
    let live = true;
    setState('loading');
    api<VacancyFitBreakdown>(`/profiles/${encodeURIComponent(profileId)}/results/${encodeURIComponent(vacancyId)}`)
      .then((r) => { if (live) { setData(r); setState('idle'); } })
      .catch((err) => { if (live) { setData(null); setState(err instanceof ApiError && err.status === 404 ? 'missing' : 'error'); } });
    return () => { live = false; };
  }, [profileId, vacancyId, nonce]);
  return { data, state, retry: () => setNonce((n) => n + 1) };
}
