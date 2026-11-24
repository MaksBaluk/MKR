import { useId } from 'react';
import { inQuadrant, QUADRANT_TEXT, type Matrix, type MatrixPoint, type Quadrant } from '@/lib/marketMatrix';

const W = 560;
const H = 340;
const M = { l: 44, r: 12, t: 12, b: 40 };
const FILL: Record<Quadrant, string> = {
  strong_wanted: 'fill-success', wanted_gap: 'fill-warning', strong_rare: 'fill-primary', rare_gap: 'fill-line-strong',
};
const TINT: Record<Quadrant, string> = {
  strong_wanted: 'bg-success-soft', wanted_gap: 'bg-warning-soft', strong_rare: 'bg-primary-soft', rare_gap: 'bg-surface-muted',
};
const ORDER: Quadrant[] = ['strong_wanted', 'wanted_gap', 'strong_rare', 'rare_gap'];

/** Demand axis ends at the next ten above the largest listed demand, so points are not squeezed into a corner. */
const xMax = (m: Matrix) => Math.max(10, Math.ceil(Math.max(m.demandCut, ...m.points.map((p) => p.demand), ...m.ungraded.map((u) => u.demand)) / 10) * 10);

/**
 * Skills of the selected market segment: how many vacancies ask for each (x) against the candidate's interview grade (y).
 * Both axes are measured values; the quadrants only sort skills for reading, they are not a recommendation score.
 */
export function MarketMatrix({ matrix }: { matrix: Matrix }) {
  const id = useId();
  const max = xMax(matrix);
  const px = (v: number) => M.l + ((W - M.l - M.r) * v) / max;
  const py = (v: number) => M.t + ((H - M.t - M.b) * (100 - v)) / 100;
  const numbered = ORDER.flatMap((q) => inQuadrant(matrix, q));
  const index = new Map(numbered.map((p, i) => [p.id, i + 1]));
  const summary = `Діаграма: ${matrix.points.length} навичок із оцінкою співбесіди. `
    + ORDER.map((q) => `${QUADRANT_TEXT[q].title}: ${inQuadrant(matrix, q).length}`).join('; ') + '.';
  const x0 = px(matrix.demandCut);
  const y0 = py(matrix.scoreCut);
  return (
    <div className="flex flex-col gap-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-labelledby={`${id}-t`}>
        <title id={`${id}-t`}>{summary}</title>
        <rect x={x0} y={M.t} width={W - M.r - x0} height={y0 - M.t} className="fill-success-soft" />
        <rect x={x0} y={y0} width={W - M.r - x0} height={H - M.b - y0} className="fill-warning-soft" />
        <rect x={M.l} y={M.t} width={x0 - M.l} height={y0 - M.t} className="fill-primary-soft" />
        <rect x={M.l} y={y0} width={x0 - M.l} height={H - M.b - y0} className="fill-surface-muted" />
        {[0, 25, 50, 75, 100].map((v) => (
          <g key={v}>
            <line x1={M.l} x2={W - M.r} y1={py(v)} y2={py(v)} className="stroke-line" strokeWidth="0.6" />
            <text x={M.l - 6} y={py(v) + 4} textAnchor="end" className="fill-ink-muted text-[10px]">{v}%</text>
          </g>
        ))}
        {Array.from({ length: max / 10 + 1 }, (_, i) => i * 10).filter((v) => v % 20 === 0 || max <= 40).map((v) => (
          <text key={v} x={px(v)} y={H - M.b + 16} textAnchor="middle" className="fill-ink-muted text-[10px]">{v}%</text>
        ))}
        <line x1={x0} x2={x0} y1={M.t} y2={H - M.b} className="stroke-ink-subtle" strokeDasharray="4 3" />
        <line x1={M.l} x2={W - M.r} y1={y0} y2={y0} className="stroke-ink-subtle" strokeDasharray="4 3" />
        <text x={(M.l + W - M.r) / 2} y={H - 6} textAnchor="middle" className="fill-ink-muted text-[11px]">Частка вакансій, які потребують навичку</text>
        <text transform={`translate(11 ${(M.t + H - M.b) / 2}) rotate(-90)`} textAnchor="middle" className="fill-ink-muted text-[11px]">Ваша оцінка співбесіди</text>
        {numbered.map((p) => (
          <g key={p.id}>
            <title>{`${p.name}: у ${p.demand}% вакансій, ваша оцінка ${p.score}%`}</title>
            <circle cx={px(p.demand)} cy={py(p.score)} r="10" className={`${FILL[p.quadrant]} stroke-surface`} strokeWidth="1.5" />
            <text x={px(p.demand)} y={py(p.score) + 3.5} textAnchor="middle" className="fill-on-primary text-[10px] font-semibold">{index.get(p.id)}</text>
          </g>
        ))}
      </svg>
      <p className="text-xs text-ink-subtle">
        Пунктир по горизонталі — «високий» рівень оцінки (75%). Пунктир по вертикалі — медіана попиту за переліком (близько {Math.round(matrix.demandCut)}% вакансій).
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {ORDER.map((q) => {
          const list: MatrixPoint[] = inQuadrant(matrix, q);
          return (
            <section key={q} className={`rounded-xl p-3 ${TINT[q]}`} aria-label={QUADRANT_TEXT[q].title}>
              <h4 className="text-sm font-semibold text-ink">{QUADRANT_TEXT[q].title} <span className="font-normal text-ink-muted">({list.length})</span></h4>
              <p className="text-xs text-ink-muted">{QUADRANT_TEXT[q].hint}</p>
              {list.length > 0 && (
                <ul className="mt-2 flex flex-col gap-0.5 text-sm text-ink">
                  {list.map((p) => (
                    <li key={p.id} className="flex items-baseline justify-between gap-2">
                      <span><span className="tabular-nums text-ink-subtle">{index.get(p.id)}.</span> {p.name}</span>
                      <span className="shrink-0 text-xs tabular-nums text-ink-muted">попит {p.demand}% · ви {p.score}%</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
      {matrix.ungraded.length > 0 && (
        <p className="text-sm text-ink-muted">
          Співбесіда не оцінила: {matrix.ungraded.map((u) => `${u.name} (${u.demand}%)`).join(', ')}. Їх не показано на діаграмі, щоб не виглядало, ніби ви цього не вмієте.
        </p>
      )}
    </div>
  );
}
