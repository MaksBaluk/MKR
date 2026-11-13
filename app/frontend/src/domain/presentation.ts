/**
 * Presentation-only mapping of a backend match row. It never recomputes S/F/U, Match, Coverage or R:
 * the backend owns every formula (see backend/domain/matching.py).
 */
export type MatchRow = {
  s: number; f: number; u: number; required_class: number;
  match: number | null; coverage: number | null; r_score: number | null;
};

const pct = (value: number | null): string => (value === null ? '—' : `${Math.round(value * 100)}%`);

export function summarize(row: MatchRow) {
  const total = row.s + row.f + row.u;
  const assessed = row.s + row.f;
  const headline = total === 0
    ? 'У вакансії немає вимог для оцінки'
    : assessed === 0
      ? 'Поки немає оцінених вимог'
      : `${row.s} із ${total} вимог відповідають наявним оцінкам (${pct(row.r_score)})`;
  const mandatoryLabel = row.required_class === 2
    ? 'Обов\'язкові вимоги виконано за наявними даними'
    : row.required_class === 1
      ? 'Обов\'язкові вимоги ще не повністю оцінені'
      : 'Є невиконана обов\'язкова вимога';
  const matchLabel = total === 0 ? 'Вимог немає' : assessed === 0
    ? 'Поки немає оцінених вимог'
    : `Серед оцінених вимог: ${pct(row.match)} (${row.s}/${assessed})`;
  return {
    headline,
    coverageLabel: `Оцінено: ${pct(row.coverage)}`,
    unknownLabel: `Невідомо: ${row.u}`,
    mandatoryLabel,
    matchLabel,
    mandatoryTone: row.required_class === 2 ? 'green' : row.required_class === 1 ? 'orange' : 'red',
  } as const;
}
