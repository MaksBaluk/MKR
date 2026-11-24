import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, HelpCircle } from 'lucide-react';
import { api, ApiError } from '@/api';
import { Badge } from '@/components/ui/badge';
import { summaryChips } from '@/lib/vacancyFit';
import type { VacancyFitBreakdown } from '@/types';

const CHIP_ICON = { met: CheckCircle2, gap: AlertTriangle, unknown: HelpCircle } as const;

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
