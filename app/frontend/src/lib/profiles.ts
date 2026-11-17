/** Pure helpers for candidate profiles: form validation (mirrors API limits), labels, active profile after archive. */

export const TRACKS = [
  { value: 'python', label: 'Python-розробка' },
  { value: 'marketing', label: 'Маркетинг' },
  { value: 'design', label: 'Дизайн' },
] as const;

export function trackLabel(track: string | null): string {
  if (!track) return 'Напрям не обрано';
  return TRACKS.find((t) => t.value === track)?.label ?? track;
}

export const LEVELS = [
  { value: 'junior', label: 'Junior' },
  { value: 'middle', label: 'Middle' },
  { value: 'senior', label: 'Senior' },
  { value: 'lead', label: 'Lead' },
] as const;

export const WORK_MODES_PROFILE = [
  { value: 'remote', label: 'Віддалено' },
  { value: 'hybrid', label: 'Гібрид' },
  { value: 'office', label: 'Офіс' },
  { value: 'any', label: 'Не важливо' },
] as const;

export interface ProfileForm {
  name: string;
  /** '' means not chosen yet: there is no default direction. */
  track: string;
  desired_title: string;
  target_level: string;
  work_mode: string;
  years: string;
  location: string;
}

export interface ProfileBody {
  name: string;
  track: string | null;
  desired_title: string;
  target_level: string | null;
  work_mode: string | null;
  years_experience: number | null;
  location: string;
}

export type ProfileFormErrors = Partial<Record<keyof ProfileForm, string>>;

type ProfileLike = {
  name: string; track: string | null; desired_title: string; target_level: string | null; work_mode: string | null;
  years_experience: number | null; location: string;
};

export function profileFormFrom(p: ProfileLike | null): ProfileForm {
  if (!p) return { name: '', track: '', desired_title: '', target_level: '', work_mode: '', years: '', location: '' };
  return {
    name: p.name, track: p.track ?? '', desired_title: p.desired_title, target_level: p.target_level ?? '',
    work_mode: p.work_mode ?? '', years: p.years_experience?.toString() ?? '', location: p.location,
  };
}

/** The candidate can start the interview: direction, level and years of experience are known. */
export function isProfileComplete(p: { track: string | null; target_level: string | null; years_experience: number | null } | null): boolean {
  return Boolean(p && p.track && p.target_level && p.years_experience !== null && p.years_experience !== undefined);
}

/** Client-side checks with the same limits as `ProfileBody` on the server; the server stays the authority. */
export function validateProfileForm(f: ProfileForm): { errors: ProfileFormErrors; body: ProfileBody | null } {
  const errors: ProfileFormErrors = {};
  const name = f.name.trim();
  const title = f.desired_title.trim();
  const location = f.location.trim();
  const yearsText = f.years.trim();
  if (name.length < 2) errors.name = 'Назва профілю має містити щонайменше 2 символи.';
  else if (name.length > 120) errors.name = 'Назва профілю — до 120 символів.';
  if (f.track !== '' && !TRACKS.some((t) => t.value === f.track)) errors.track = 'Оберіть напрям.';
  if (f.target_level !== '' && !LEVELS.some((l) => l.value === f.target_level)) errors.target_level = 'Оберіть рівень.';
  if (f.work_mode !== '' && !WORK_MODES_PROFILE.some((m) => m.value === f.work_mode)) errors.work_mode = 'Оберіть формат роботи.';
  if (title.length > 160) errors.desired_title = 'Бажана посада — до 160 символів.';
  const years = yearsText === '' ? null : Number(yearsText);
  if (years !== null && (!/^\d+$/.test(yearsText) || years > 70)) errors.years = 'Вкажіть ціле число років від 0 до 70.';
  if (location.length > 120) errors.location = 'Локація — до 120 символів.';
  if (Object.keys(errors).length) return { errors, body: null };
  return {
    errors,
    body: {
      name, track: f.track || null, desired_title: title, target_level: f.target_level || null,
      work_mode: f.work_mode || null, years_experience: years, location,
    },
  };
}

/** Which profile is active after `archivedId` is archived: unchanged, or the first remaining one. */
export function activeAfterArchive(profiles: readonly { id: string }[], archivedId: string, activeId: string | null): string | null {
  const rest = profiles.filter((p) => p.id !== archivedId);
  if (activeId && activeId !== archivedId && rest.some((p) => p.id === activeId)) return activeId;
  return rest[0]?.id ?? null;
}

const STATUS_LABELS: Record<string, string> = { ACTIVE: 'Активна', PAUSED: 'Призупинена', FINISHED: 'Завершена' };

export function attemptStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

/** Start button text. `attempts` is null when the history is not loaded yet. */
export function startLabel(attemptsCount: number, attempts: readonly { status: string }[] | null): string {
  if (attemptsCount === 0) return 'Пройти співбесіду';
  if (attempts?.some((a) => a.status !== 'FINISHED')) return 'Продовжити співбесіду';
  return 'Пройти ще раз';
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('uk-UA', { day: 'numeric', month: 'long', year: 'numeric' }).format(d);
}

/** Profile-scoped self-ratings as a map; `null` means not rated, and a rated 0 stays 0. */
export function ratingsMap(items: { action_id: string; value: number | null }[]): Record<string, number | null> {
  return Object.fromEntries(items.map((i) => [i.action_id, i.value]));
}
