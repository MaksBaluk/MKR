import { levelSegments, type DistributionRow } from '@/lib/marketChart';

const SEGMENT_FILL: Record<string, string> = { low: 'bg-accent', mid: 'bg-primary', high: 'bg-brand-deep' };

/**
 * Share of the track's vacancies that require each action. The filled part of a bar is split by the level those
 * vacancies ask for (low / middle / high), so «78% need it, mostly at a middle level» reads at a glance.
 */
export function MarketDistributionChart({ rows, caption }: { rows: DistributionRow[]; caption: string }) {
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="text-sm text-ink-muted">{caption}</figcaption>
      <p className="flex flex-wrap gap-4 text-xs text-ink-muted">
        {levelSegments({ low: 1, mid: 1, high: 1 }).map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className={`size-3 rounded-sm ${SEGMENT_FILL[s.key]}`} />Рівень вимоги: {s.label.toLowerCase()}
          </span>
        ))}
      </p>
      <ul className="flex flex-col gap-2" aria-label={caption}>
        {rows.map((r) => {
          const segments = r.levels ? levelSegments(r.levels) : [];
          const main = segments.length ? segments.reduce((a, b) => (b.count > a.count ? b : a)) : null;
          const detail = segments.map((s) => `${s.label.toLowerCase()} ${s.percent}%`).join(', ');
          return (
            <li key={r.id} className="grid items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)_auto]">
              <span className="min-w-0 text-sm font-medium text-ink [overflow-wrap:anywhere]">{r.name}</span>
              <span className="flex items-center gap-2">
                <span className="relative h-3 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-muted" role="img"
                  aria-label={`${r.name}: потрібна у ${r.share}% вакансій${detail ? `; рівень вимоги: ${detail}` : ''}`}>
                  <span className="flex h-full overflow-hidden rounded-full" style={{ width: `${r.share}%` }}>
                    {segments.map((s) => (
                      <span key={s.key} className={`h-full ${SEGMENT_FILL[s.key]}`} style={{ width: `${s.percent}%` }} title={`${s.label}: ${s.percent}%`} />
                    ))}
                    {segments.length === 0 && <span className="h-full w-full bg-primary" />}
                  </span>
                </span>
                <span className="w-10 shrink-0 text-right text-xs tabular-nums text-ink-muted">{r.share}%</span>
              </span>
              <span className="text-xs text-ink-muted sm:w-48 sm:text-right">
                {main && main.count > 0 ? `переважно ${main.label.toLowerCase()} (${main.percent}%)` : ''}
              </span>
            </li>
          );
        })}
      </ul>
      <details className="text-sm">
        <summary className="cursor-pointer text-ink-muted hover:text-ink">Таблиця значень</summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr>
              <th scope="col" className="py-1 font-semibold">Компетентність</th>
              <th scope="col" className="py-1 text-right font-semibold">Частка вакансій</th>
              <th scope="col" className="py-1 text-right font-semibold">Низький</th>
              <th scope="col" className="py-1 text-right font-semibold">Середній</th>
              <th scope="col" className="py-1 text-right font-semibold">Високий</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const s = r.levels ? levelSegments(r.levels) : [];
              return (
                <tr key={r.id} className="border-t border-line">
                  <td className="py-1">{r.name}</td>
                  <td className="py-1 text-right tabular-nums">{r.share}%</td>
                  {[0, 1, 2].map((i) => <td key={i} className="py-1 text-right tabular-nums">{s[i] ? `${s[i].percent}%` : '—'}</td>)}
                </tr>
              );
            })}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
