import type { ReactNode } from 'react';
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  SENIORITY_LABELS, WORK_MODE_LABELS, compareRows, donutRows, kindRows, salaryRows,
  type MarketOverview,
} from '@/lib/marketOverview';

const PALETTE = ['var(--color-primary)', 'var(--color-accent)', 'var(--color-warning)', 'var(--color-info)'];

function ChartCard({ title, description, children, table, className }: {
  title: string; description: string; children: ReactNode; table: ReactNode; className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader><CardTitle>{title}</CardTitle><CardDescription>{description}</CardDescription></CardHeader>
      <CardContent className="flex flex-col gap-3">
        {children}
        <details className="text-sm">
          <summary className="cursor-pointer text-ink-muted hover:text-ink">Таблиця значень</summary>
          <div className="mt-2 overflow-x-auto">{table}</div>
        </details>
      </CardContent>
    </Card>
  );
}

function Donut({ rows, total, label }: { rows: { key: string; label: string; value: number; percent: number }[]; total: number; label: string }) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="relative size-44 shrink-0" role="img"
        aria-label={`${label}: ${rows.map((r) => `${r.label} ${r.value} (${r.percent}%)`).join(', ')}`}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={rows} dataKey="value" nameKey="label" innerRadius="60%" outerRadius="95%" paddingAngle={2} isAnimationActive={false}>
              {rows.map((r, i) => <Cell key={r.key} fill={PALETTE[i % PALETTE.length]} />)}
            </Pie>
            <Tooltip formatter={(v: number) => `${v} вакансій`} />
          </PieChart>
        </ResponsiveContainer>
        <span className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-2xl font-bold tabular-nums text-ink">{total}</span>
          <span className="text-xs text-ink-subtle">вакансій</span>
        </span>
      </div>
      <ul className="flex flex-col gap-1.5 text-sm">
        {rows.map((r, i) => (
          <li key={r.key} className="flex items-center gap-2">
            <span aria-hidden="true" className="size-3 rounded-sm" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="text-ink">{r.label}</span>
            <span className="tabular-nums text-ink-muted">{r.value} · {r.percent}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const Table = ({ head, rows }: { head: string[]; rows: (string | number)[][] }) => (
  <table className="w-full text-left text-sm">
    <thead><tr>{head.map((h) => <th key={h} scope="col" className="py-1 pr-3 font-semibold">{h}</th>)}</tr></thead>
    <tbody>{rows.map((r) => <tr key={String(r[0])} className="border-t border-line">{r.map((c, i) => <td key={i} className="py-1 pr-3 tabular-nums">{c}</td>)}</tr>)}</tbody>
  </table>
);

export function MarketCharts({ overview, competencies }: {
  overview: MarketOverview;
  competencies: { action_id: string; action_name: string; interview_score: number | null }[] | null;
}) {
  const seniority = donutRows(overview.seniority, SENIORITY_LABELS);
  const mode = donutRows(overview.work_mode, WORK_MODE_LABELS);
  const salary = salaryRows(overview.salary);
  const drawn = salary.filter((s) => s.enough);
  const kinds = kindRows(overview.requirement_kinds);
  const maxKind = Math.max(1, ...kinds.map((k) => k.total));
  const compare = compareRows(overview.requirement_kinds, competencies ?? []);
  const currency = overview.salary[0]?.currency ?? '';

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <ChartCard title="Рівні вакансій" description="Скільки вакансій добірки на кожен рівень."
        table={<Table head={['Рівень', 'Вакансій', 'Частка']} rows={seniority.map((r) => [r.label, r.value, `${r.percent}%`])} />}>
        <Donut rows={seniority} total={overview.vacancies_total} label="Рівні вакансій" />
      </ChartCard>
      <ChartCard title="Формат роботи" description="Офіс, гібрид чи віддалено."
        table={<Table head={['Формат', 'Вакансій', 'Частка']} rows={mode.map((r) => [r.label, r.value, `${r.percent}%`])} />}>
        <Donut rows={mode} total={overview.vacancies_total} label="Формат роботи" />
      </ChartCard>
      <ChartCard className="md:col-span-2" title="Зарплатні вилки за рівнем"
        description={`Від мінімуму до максимуму${currency ? `, ${currency}` : ''}. Лише вакансії з вказаною зарплатою; рівні з менш ніж трьома вакансіями не малюються.`}
        table={<Table head={['Рівень', 'Вакансій', 'Мін', 'Середнє', 'Макс']} rows={salary.map((s) => [s.label, s.count, s.min, s.avg, s.max])} />}>
        {drawn.length === 0 ? <p className="text-sm text-ink-muted">Замало даних про зарплати.</p> : (
          <div className="h-72" role="img" aria-label={`Зарплатні вилки: ${drawn.map((s) => `${s.label} від ${s.min} до ${s.max}`).join('; ')}`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={drawn} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(_v: number, _n: string, p) => `${p.payload.min}–${p.payload.max} (середнє ${p.payload.avg})`} />
                <Bar dataKey="base" stackId="s" fill="transparent" isAnimationActive={false} />
                <Bar dataKey="range" stackId="s" name="Вилка" fill="var(--color-primary)" radius={4} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </ChartCard>
      <ChartCard className="md:col-span-2" title="Обов’язкове чи бажане"
        description="Для топ-8 компетентностей: у скількох вакансій навичка обов’язкова, а в скількох лише бажана."
        table={<Table head={['Компетентність', 'Обов’язково', 'Бажано']} rows={kinds.map((k) => [k.name, k.mandatory, k.desired])} />}>
        <ul className="flex flex-col gap-2" aria-label="Обов’язкове чи бажане по компетентностях">
          {kinds.map((k) => (
            <li key={k.id} className="grid items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)_auto]">
              <span className="min-w-0 text-sm font-medium text-ink [overflow-wrap:anywhere]">{k.name}</span>
              <span className="flex h-4 overflow-hidden rounded-full bg-surface-muted" role="img"
                aria-label={`${k.name}: обов’язково у ${k.mandatory} вакансій, бажано у ${k.desired}`}>
                <span className="h-full bg-primary" style={{ width: `${(100 * k.mandatory) / maxKind}%` }} />
                <span className="h-full bg-accent" style={{ width: `${(100 * k.desired) / maxKind}%` }} />
              </span>
              <span className="text-xs tabular-nums text-ink-muted sm:w-44 sm:text-right">
                обов’язково {k.mandatory} · бажано {k.desired}
              </span>
            </li>
          ))}
        </ul>
        <p className="flex flex-wrap gap-4 text-xs text-ink-muted">
          <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="size-3 rounded-sm bg-primary" />Обов’язково</span>
          <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="size-3 rounded-sm bg-accent" />Бажано</span>
        </p>
      </ChartCard>
      <ChartCard className="md:col-span-2" title="Ваш рівень проти вимог ринку"
        description="Топ-8 навичок за попитом: який рівень у середньому вимагають вакансії і яку оцінку ви отримали в співбесіді."
        table={<Table head={['Компетентність', 'Вимоги ринку, %', 'Ваша оцінка, %']} rows={compare.map((r) => [r.name, r.market, r.candidate ?? 'немає оцінки'])} />}>
        <ul className="flex flex-col gap-3" aria-label="Ваш рівень проти вимог ринку">
          {compare.map((r) => (
            <li key={r.id} className="grid items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)]">
              <span className="min-w-0 text-sm font-medium text-ink [overflow-wrap:anywhere]">{r.name}</span>
              <span className="flex flex-col gap-1.5">
                <span className="flex items-center gap-2">
                  <span className="w-20 shrink-0 text-xs text-ink-muted">Ринок</span>
                  <span className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-muted" role="img" aria-label={`${r.name}: ринок вимагає ${r.market}%`}>
                    <span className="block h-full rounded-full bg-primary" style={{ width: `${r.market}%` }} />
                  </span>
                  <span className="w-20 shrink-0 text-right text-xs tabular-nums text-ink-muted">{r.market}%</span>
                </span>
                <span className="flex items-center gap-2">
                  <span className="w-20 shrink-0 text-xs text-ink-muted">Ви</span>
                  <span className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-muted" role="img"
                    aria-label={r.candidate === null ? `${r.name}: немає оцінки` : `${r.name}: ваша оцінка ${r.candidate}%`}>
                    {r.candidate === null
                      ? <span className="block h-full w-full bg-[repeating-linear-gradient(135deg,var(--color-line-strong)_0_2px,transparent_2px_6px)]" />
                      : <span className="block h-full rounded-full bg-accent" style={{ width: `${r.candidate}%` }} />}
                  </span>
                  <span className="w-20 shrink-0 text-right text-xs tabular-nums text-ink-muted">{r.candidate === null ? 'немає оцінки' : `${r.candidate}%`}</span>
                </span>
              </span>
            </li>
          ))}
        </ul>
      </ChartCard>
    </div>
  );
}
