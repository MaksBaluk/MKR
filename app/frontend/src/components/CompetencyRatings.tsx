import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { api, ApiError } from '@/api';
import { ErrorRetry } from '@/components/ErrorRetry';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { bandFor } from '@/lib/bands';
import { mergeCompetencyRows, type CompetencyRow } from '@/lib/competencyRows';
import { diffChip, rowSummary } from '@/lib/competencyScale';
import type { CompetencyResult, SelfRatingValue } from '@/types';

type SaveState = 'idle' | 'saving' | 'saved';
interface Action { id: string; label_uk: string }

const VISIBLE = 6;
const pct = (v: number) => Math.round(v * 100);

/** Compact rows, two per line on wide screens: name, the interview grade (read-only) and the self-rating slider. */
export function CompetencyRatings({ track, profileId, competencies }: {
  track: string; profileId: string; competencies: CompetencyResult[];
}) {
  const [actions, setActions] = useState<Action[] | null>(null);
  const [importance, setImportance] = useState<Record<string, number>>({});
  const [values, setValues] = useState<Record<string, number | null>>({});
  const [state, setState] = useState<Record<string, SaveState>>({});
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [nonce, setNonce] = useState(0);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const pid = encodeURIComponent(profileId);
  const graded = competencies.some((c) => c.interview_score !== null);

  useEffect(() => {
    let live = true;
    setError(null);
    setActions(null);
    Promise.all([
      api<Action[]>(`/competencies?track=${encodeURIComponent(track)}`),
      api<{ items: SelfRatingValue[] }>(`/profiles/${pid}/self-ratings`),
      api<{ items: { action_id: string; share_percent: number }[] }>(`/market/distribution?track=${encodeURIComponent(track)}`)
        .catch(() => ({ items: [] })),
    ])
      .then(([a, r, d]) => {
        if (!live) return;
        setImportance(Object.fromEntries(d.items.map((i) => [i.action_id, i.share_percent])));
        setValues(Object.fromEntries(r.items.map((x) => [x.action_id, x.value])));
        setActions(a);
      })
      .catch((err) => live && setError(err instanceof ApiError ? err.message : 'Не вдалося завантажити компетентності.'));
    return () => {
      live = false;
    };
  }, [track, pid, nonce]);

  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);

  // The order is fixed once the lists are loaded, so a row never jumps away while its slider is dragged.
  const order = useMemo(
    () => (actions ? mergeCompetencyRows(actions, competencies, {}, importance).map((r) => r.id) : []),
    [actions, competencies, importance],
  );
  const rows = useMemo(() => {
    if (!actions) return [];
    const byId = new Map(mergeCompetencyRows(actions, competencies, values, importance).map((r) => [r.id, r]));
    return order.map((id) => byId.get(id)).filter((r): r is CompetencyRow => !!r);
  }, [actions, competencies, values, importance, order]);

  async function persist(actionId: string, value: number | null) {
    setState((s) => ({ ...s, [actionId]: 'saving' }));
    setSaveError(null);
    try {
      await api(`/profiles/${pid}/self-ratings/${actionId}`, { method: 'PUT', json: { value } });
      setState((s) => ({ ...s, [actionId]: 'saved' }));
    } catch (err) {
      setState((s) => ({ ...s, [actionId]: 'idle' }));
      setSaveError(err instanceof ApiError ? err.message : 'Не вдалося зберегти оцінку.');
    }
  }

  function change(actionId: string, value: number | null) {
    setValues((v) => ({ ...v, [actionId]: value }));
    clearTimeout(timers.current[actionId]);
    timers.current[actionId] = setTimeout(() => void persist(actionId, value), 400);
  }

  if (error) return <ErrorRetry message={error} onRetry={() => setNonce((n) => n + 1)} />;
  if (!actions) return <Skeleton className="h-40" />;
  if (rows.length === 0) return <p className="text-sm text-ink-muted">Для цього напряму ще немає професійних дій.</p>;
  const shown = showAll ? rows : rows.slice(0, VISIBLE);

  return (
    <div className="flex flex-col gap-3">
      {saveError && <Alert role="alert" variant="danger">{saveError}</Alert>}
      <ul className="grid gap-3 lg:grid-cols-2">
        {shown.map((r) => {
          const id = `cr-${r.id}`;
          const st = state[r.id] ?? 'idle';
          const band = r.llm === null ? null : bandFor(r.llm);
          return (
            <li key={r.id} className="flex min-w-0 flex-col gap-1.5 rounded-xl border border-line bg-canvas px-3 py-2.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <label htmlFor={id} className="min-w-0 text-sm font-semibold text-ink [overflow-wrap:anywhere]">{r.name}</label>
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs tabular-nums text-ink-muted">
                  {graded && (band
                    ? <Badge variant={band.badge} title="Оцінка співбесіди (LLM), лише для читання">LLM {pct(r.llm!)}% · {band.label}</Badge>
                    : <span className="text-ink-subtle">LLM: немає оцінки</span>)}
                  {graded && band && !r.sufficient && (
                    <span className="rounded-full border border-line-strong px-1.5 py-0.5 text-ink-subtle" title="Замало свідчень у відповідях, тому оцінка орієнтовна">
                      орієнтовна<span className="sr-only">: замало свідчень у відповідях</span>
                    </span>
                  )}
                  <span className="font-medium text-ink">Я {r.self === null ? '—' : `${pct(r.self)}%`}</span>
                  {r.diff !== null && (() => { const c = diffChip(r.diff); return (
                    <span className="rounded-full bg-surface-muted px-1.5 py-0.5 text-ink" title={c.hint}>{c.text}<span className="sr-only">: {c.hint}</span></span>
                  ); })()}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <div className="relative h-11 min-w-0 flex-1" role="group" aria-label={rowSummary(r.llm, r.self)}>
                  <div className="pointer-events-none absolute inset-x-3.5 top-1/2 h-2.5 -translate-y-1/2 overflow-hidden rounded-full bg-surface-muted">
                    {r.llm === null ? (
                      graded && <span className="absolute inset-0 bg-[repeating-linear-gradient(135deg,var(--color-line-strong)_0_2px,transparent_2px_6px)]" />
                    ) : (
                      <span className={`absolute inset-y-0 left-0 ${band!.bar} transition-[width] motion-reduce:transition-none`} style={{ width: `${pct(r.llm)}%` }} />
                    )}
                  </div>
                  <input id={id} type="range" min={0} max={100} step={5} value={r.self === null ? 0 : pct(r.self)}
                    onChange={(e) => change(r.id, Number(e.target.value) / 100)}
                    aria-valuetext={r.self === null ? 'не вказано' : `${pct(r.self)} зі 100`}
                    className={`absolute inset-0 m-0 h-full w-full cursor-pointer appearance-none bg-transparent focus-visible:outline-none
                      [&::-webkit-slider-runnable-track]:h-11 [&::-webkit-slider-runnable-track]:bg-transparent
                      [&::-moz-range-track]:h-11 [&::-moz-range-track]:bg-transparent
                      [&::-webkit-slider-thumb]:mt-2 [&::-webkit-slider-thumb]:size-7 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-[3px] [&::-webkit-slider-thumb]:border-primary [&::-webkit-slider-thumb]:bg-canvas [&::-webkit-slider-thumb]:shadow-sm
                      [&::-moz-range-thumb]:size-6 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-[3px] [&::-moz-range-thumb]:border-primary [&::-moz-range-thumb]:bg-canvas
                      focus-visible:[&::-webkit-slider-thumb]:ring-2 focus-visible:[&::-webkit-slider-thumb]:ring-ring focus-visible:[&::-webkit-slider-thumb]:ring-offset-2
                      focus-visible:[&::-moz-range-thumb]:outline-2 focus-visible:[&::-moz-range-thumb]:outline-ring
                      ${r.self === null ? '[&::-webkit-slider-thumb]:border-dashed [&::-webkit-slider-thumb]:border-line-strong [&::-moz-range-thumb]:border-dashed [&::-moz-range-thumb]:border-line-strong' : ''}`} />
                </div>
                <button type="button" onClick={() => change(r.id, null)} disabled={r.self === null}
                  className="min-h-11 shrink-0 cursor-pointer rounded-md px-2 text-xs text-ink-muted hover:bg-surface-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:invisible">
                  Не оцінювати<span className="sr-only">: {r.name}</span>
                </button>
              </div>
              <div className="flex min-h-4 items-start justify-between gap-2 text-xs text-ink-muted">
                {r.reason ? (
                  <details className="min-w-0 flex-1">
                    <summary className="cursor-pointer text-primary-strong underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring">Чому така оцінка</summary>
                    <p className="mt-1">{r.reason}</p>
                  </details>
                ) : <span />}
                <span className="flex shrink-0 items-center gap-1" aria-live="polite">
                  {st === 'saving' && <Loader2 className="size-3 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
                  {st === 'saved' && <CheckCircle2 className="size-3 text-success-ink" aria-hidden="true" />}
                  {st === 'saving' ? 'Зберігаємо…' : st === 'saved' ? 'Збережено' : ''}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
      {rows.length > VISIBLE && (
        <Button variant="outline" size="sm" className="self-start" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
          {showAll ? 'Показати менше' : `Показати всі (${rows.length})`}
        </Button>
      )}
    </div>
  );
}
