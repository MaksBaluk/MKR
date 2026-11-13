const percentFormat = new Intl.NumberFormat('uk-UA', { style: 'percent', maximumFractionDigits: 0 });

/** Ratio in [0,1] → "27%". `null` means "not evaluable", never 0%. */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return percentFormat.format(value);
}

export function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat('uk-UA', { style: 'currency', currency, maximumFractionDigits: 0 }).format(value);
}

export function formatSalary(min: number | null, max: number | null, currency: string): string {
  if (min == null && max == null) return 'Зарплата не вказана';
  if (min != null && max != null) return `${formatCurrency(min, currency)} – ${formatCurrency(max, currency)}`;
  return formatCurrency((min ?? max) as number, currency);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('uk-UA', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
}
