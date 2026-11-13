import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from 'recharts';
import { Button } from '@/components/ui/button';
import { buildChartRows, type ChartRow } from '@/lib/marketChart';
import type { CompetencyResult, MarketSkill, SelfRatingValue } from '@/types';

const TOP = 10;
const ROW = 40;

const BAND_FILL: Record<NonNullable<ChartRow['band']>, string> = {
  Високий: 'var(--color-success)',
  Середній: 'var(--color-primary)',
  Низький: 'var(--color-warning)',
};

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

const levelText = (r: ChartRow) => (r.band ? `${r.band} рівень` : 'Не оцінено');

interface ShapeProps {
  x?: number; y?: number; width?: number; height?: number;
  payload?: ChartRow;
  background?: { x: number; y: number; width: number; height: number };
  hatchId: string;
}

/** Track + level bar (or hatching when unassessed) + thin self-rating marker, all on one 0–100 track. */
function RowShape({ x = 0, y = 0, width = 0, height = 0, payload, background, hatchId }: ShapeProps) {
  if (!payload || !background) return null;
  const bh = Math.min(height, 16);
  const by = y + (height - bh) / 2;
  const selfX = payload.self === null ? null : background.x + (payload.self / 100) * background.width;
  return (
    <g>
      <rect x={background.x} y={by} width={background.width} height={bh} rx={bh / 2}
        style={{ fill: payload.level === null ? `url(#${hatchId})` : 'var(--color-surface-muted)' }} />
      {payload.level !== null && width > 0 && (
        <rect x={x} y={by} width={Math.max(width, bh)} height={bh} rx={bh / 2}
          style={{ fill: payload.band ? BAND_FILL[payload.band] : 'var(--color-primary)' }} />
      )}
      {selfX !== null && (
        <rect x={selfX - 1.5} y={by - 5} width={3} height={bh + 10} rx={1.5} style={{ fill: 'var(--color-ink)' }} />
      )}
    </g>
  );
}

function Tick({ x = 0, y = 0, payload, maxChars, rows }: {
  x?: number; y?: number; payload?: { value: string }; maxChars: number; rows: ChartRow[];
}) {
  const row = rows.find((r) => r.action_id === payload?.value);
  if (!row) return null;
  const full = `${row.order}. ${row.name}`;
  const text = full.length > maxChars ? `${full.slice(0, maxChars - 1).trimEnd()}…` : full;
  return (
    <text x={x - 8} y={y} dy={4} textAnchor="end" style={{ fill: 'var(--color-ink)', fontSize: 13 }}>
      <title>{full}</title>
      {text}
    </text>
  );
}

function ChartTooltip({ active, payload }: TooltipProps<number, string>) {
  const row = payload?.[0]?.payload as ChartRow | undefined;
  if (!active || !row) return null;
  return (
    <div className="max-w-64 rounded-xl border border-line bg-surface p-3 text-sm shadow-raised">
      <p className="font-semibold text-ink">{row.order}. {row.name}</p>
      <p className="mt-1 text-ink-muted">
        За співбесідою: {levelText(row)}
        {row.level !== null && <span className="text-ink-subtle"> ({row.level} з 100)</span>}
      </p>
      <p className="text-ink-muted">Самооцінка: {row.self === null ? 'не вказано' : `${row.self} з 100`}</p>
    </div>
  );
}

export function ChartLegend() {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-ink-muted" aria-label="Умовні позначення">
      <li className="flex items-center gap-2">
        <span aria-hidden="true" className="h-3 w-6 rounded-full bg-primary" />Ваш рівень за співбесідою
      </li>
      <li className="flex items-center gap-2">
        <span aria-hidden="true" className="h-4 w-[3px] rounded-sm bg-ink" />Самооцінка
      </li>
      <li className="flex items-center gap-2">
        <span aria-hidden="true" className="bg-hatch h-3 w-6 rounded-full border border-line-strong" />Не оцінено
      </li>
    </ul>
  );
}

/**
 * Candidate's level for the cohort's most common professional actions, in market order.
 * Shows only the order and names of market skills, never market counts or shares.
 */
export function MarketChart({ market, competencies, selfRatings, title = 'Ваш рівень у найпоширеніших навичках добірки' }: {
  market: MarketSkill[];
  competencies: CompetencyResult[];
  selfRatings: SelfRatingValue[];
  title?: string;
}) {
  const [showAll, setShowAll] = useState(false);
  const [asTable, setAsTable] = useState(false);
  const reduced = usePrefersReducedMotion();
  const [boxRef, width] = useWidth<HTMLDivElement>();
  const hatchId = `hatch-${useId().replace(/:/g, '')}`;
  const headingId = `${hatchId}-title`;
  const rows = useMemo(() => buildChartRows(market, competencies, selfRatings, showAll ? undefined : TOP),
    [market, competencies, selfRatings, showAll]);
  const narrow = width > 0 && width < 480;
  const axisWidth = narrow ? Math.max(96, Math.round(width * 0.42)) : 240;
  const maxChars = Math.floor(axisWidth / 7.2);
  const assessed = rows.filter((r) => r.level !== null).length;

  if (market.length === 0)
    return <p className="text-sm text-ink-muted">Для цієї добірки ще немає переліку поширених навичок.</p>;

  return (
    <figure className="flex min-w-0 flex-col gap-3" aria-labelledby={headingId}>
      <figcaption id={headingId} className="text-base font-semibold text-ink">{title}</figcaption>
      <p className="text-sm text-ink-muted">
        Навички впорядковано від найпоширенішої у вакансіях вашої добірки. Довжина смуги — ваш рівень за відповідями.
      </p>
      <ChartLegend />
      <div ref={boxRef} className="w-full min-w-0">
      {!asTable && (
        <div role="img"
          aria-label={`Діаграма: ${rows.length} навичок у порядку поширеності, оцінено ${assessed}. Детальні значення доступні в таблиці.`}>
          <ResponsiveContainer width="100%" height={rows.length * ROW + 8}>
            <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 12, bottom: 4, left: 0 }} barCategoryGap={8}>
              <defs>
                <pattern id={hatchId} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <rect width="6" height="6" style={{ fill: 'var(--color-surface)' }} />
                  <rect width="2" height="6" style={{ fill: 'var(--color-line-strong)' }} />
                </pattern>
              </defs>
              <XAxis type="number" domain={[0, 100]} hide />
              <YAxis type="category" dataKey="action_id" width={axisWidth} axisLine={false} tickLine={false}
                interval={0} tick={<Tick maxChars={maxChars} rows={rows} />} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--color-primary-soft)' }} />
              <Bar dataKey={(r: ChartRow) => r.level ?? 0} background isAnimationActive={!reduced}
                shape={(p: unknown) => <RowShape {...(p as ShapeProps)} hatchId={hatchId} />} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {asTable && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{title}</caption>
            <thead className="text-ink-subtle">
              <tr className="border-b border-line">
                <th scope="col" className="py-2 pr-3 font-medium">Місце</th>
                <th scope="col" className="py-2 pr-3 font-medium">Навичка</th>
                <th scope="col" className="py-2 pr-3 font-medium">Ваш рівень за співбесідою</th>
                <th scope="col" className="py-2 font-medium">Самооцінка</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.action_id} className="border-b border-line last:border-0">
                  <td className="py-2 pr-3 tabular-nums text-ink-muted">{r.order}</td>
                  <th scope="row" className="py-2 pr-3 font-medium text-ink">{r.name}</th>
                  <td className="py-2 pr-3 text-ink-muted">
                    {levelText(r)}{r.level !== null && <span className="text-ink-subtle"> ({r.level} з 100)</span>}
                  </td>
                  <td className="py-2 text-ink-muted">{r.self === null ? 'Не вказано' : `${r.self} з 100`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      </div>
      <div className="flex flex-wrap gap-2">
        {market.length > TOP && (
          <Button variant="ghost" size="sm" aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>
            {showAll ? `Показати лише перші ${TOP}` : `Показати всі (${market.length})`}
          </Button>
        )}
        <Button variant="outline" size="sm" aria-pressed={asTable} onClick={() => setAsTable(!asTable)}>
          {asTable ? 'Показати діаграмою' : 'Показати таблицею'}
        </Button>
      </div>
    </figure>
  );
}
