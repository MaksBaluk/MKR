import { LEVELS, TRACKS, WORK_MODES_PROFILE, type ProfileForm } from '@/lib/profiles';

export interface SummaryRow { key: keyof ProfileForm; label: string; value: string | null; required: boolean }

const labelOf = (list: readonly { value: string; label: string }[], v: string) => list.find((x) => x.value === v)?.label ?? null;
const yearsText = (y: string): string | null => {
  const n = y.trim();
  if (n === '') return null;
  const k = Number(n);
  return `${n} ${k % 10 === 1 && k % 100 !== 11 ? 'рік' : k % 10 >= 2 && k % 10 <= 4 && (k % 100 < 12 || k % 100 > 14) ? 'роки' : 'років'}`;
};

/** Rows of the «Поточний профіль» card from the form as typed, with the share of filled fields (form completeness only). */
export function profileSummary(f: ProfileForm): { rows: SummaryRow[]; percent: number; ready: boolean } {
  const rows: SummaryRow[] = [
    { key: 'track', label: 'Напрям', value: labelOf(TRACKS, f.track), required: true },
    { key: 'target_level', label: 'Рівень', value: labelOf(LEVELS, f.target_level), required: true },
    { key: 'years', label: 'Досвід', value: yearsText(f.years), required: true },
    { key: 'work_mode', label: 'Формат роботи', value: labelOf(WORK_MODES_PROFILE, f.work_mode), required: false },
    { key: 'location', label: 'Локація', value: f.location.trim() || null, required: false },
    { key: 'desired_title', label: 'Бажана посада', value: f.desired_title.trim() || null, required: false },
  ];
  const filled = rows.filter((r) => r.value !== null).length;
  return { rows, percent: Math.round((filled / rows.length) * 100), ready: rows.filter((r) => r.required).every((r) => r.value !== null) };
}
