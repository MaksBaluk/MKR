export interface Band {
  label: 'Високий' | 'Середній' | 'Низький';
  badge: 'success' | 'info' | 'warning';
  bar: string;
}

/** Policy bands from MATH_SPEC §3 collapsed to three display levels. Not statistical calibration. */
export function bandFor(score: number): Band {
  if (score >= 0.75) return { label: 'Високий', badge: 'success', bar: 'bg-success' };
  if (score >= 0.5) return { label: 'Середній', badge: 'info', bar: 'bg-primary' };
  return { label: 'Низький', badge: 'warning', bar: 'bg-warning' };
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] ?? '?').concat(parts[1]?.[0] ?? '').toUpperCase();
}

export function timeLabel(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' });
}
