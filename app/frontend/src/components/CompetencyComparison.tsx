import { comparisonRows } from '@/lib/results';
import type { CompetencyResult } from '@/types';

const percent = (v: number | null, empty: string) => (v === null ? empty : `${Math.round(v * 100)}%`);

/** Interview grade (read-only) and self-rating side by side. Name on its own line, values below: never overlaps. */
export function CompetencyComparison({ competencies }: { competencies: CompetencyResult[] }) {
  const rows = comparisonRows(competencies);
  if (rows.length === 0) return <p className="text-sm text-ink-muted">Порівняння буде доступне після співбесіди.</p>;
  return (
    <ul className="flex min-w-0 flex-col divide-y divide-line">
      {rows.map((r) => (
        <li key={r.name} className="py-2 text-sm">
          <p className="min-w-0 font-semibold text-ink [overflow-wrap:anywhere]">{r.name}</p>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-ink-muted">
            <dt>Співбесіда</dt><dd className="text-right tabular-nums">{percent(r.interview, 'немає оцінки')}</dd>
            <dt>Самооцінка</dt><dd className="text-right tabular-nums">{percent(r.self, 'не оцінено')}</dd>
          </dl>
        </li>
      ))}
    </ul>
  );
}
