import { Badge } from '@/components/ui/badge';
import { bandFor } from '@/lib/bands';
import type { CompetencyResult } from '@/types';

/** Read-only scale of the interview grades per topic. Every value has text, not only colour. */
export function LlmScale({ competencies }: { competencies: CompetencyResult[] }) {
  if (competencies.length === 0) return <p className="text-sm text-ink-muted">Оцінка з’явиться після співбесіди.</p>;
  return (
    <ul className="flex flex-col gap-3">
      {competencies.map((c) => {
        const score = c.interview_score;
        const band = score === null ? null : bandFor(score);
        const pct = score === null ? 0 : Math.round(score * 100);
        return (
          <li key={c.action_id} className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="min-w-0 text-sm font-semibold text-ink [overflow-wrap:anywhere]">{c.action_name}</span>
              {band ? <Badge variant={band.badge}>{band.label} · {pct}%</Badge> : <Badge>Немає оцінки</Badge>}
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-surface-muted" role="img"
              aria-label={band ? `${c.action_name}: ${band.label} рівень, ${pct} з 100` : `${c.action_name}: немає оцінки`}>
              <div className={`h-full rounded-full ${band?.bar ?? ''}`} style={{ width: `${pct}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
