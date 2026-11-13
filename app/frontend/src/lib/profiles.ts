/** Pure helpers for candidate profiles: form validation (mirrors API limits), labels, active profile after archive. */

export const TRACKS = [
  { value: 'python', label: 'Python-розробка' },
  { value: 'marketing', label: 'Маркетинг' },
  { value: 'design', label: 'Дизайн' },
] as const;

export function trackLabel(track: string): string {
  return TRACKS.find((t) => t.value === track)?.label ?? track;
}

export interface ProfileForm {
  name: string;
  track: string;
  desired_title: string;
  years: string;
  location: string;
}

export interface ProfileBody {
  name: string;
  track: string;
  desired_title: string;
  years_experience: number | null;
  location: string;
}

export type ProfileFormErrors = Partial<Record<keyof ProfileForm, string>>;

export function profileFormFrom(p: Omit<ProfileBody, 'track'> & { track: string } | null): ProfileForm {
  if (!p) return { name: '', track: 'python', desired_title: '', years: '', location: '' };
  return { name: p.name, track: p.track, desired_title: p.desired_title, years: p.years_experience?.toString() ?? '', location: p.location };
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
  if (!TRACKS.some((t) => t.value === f.track)) errors.track = 'Оберіть напрям.';
  if (title.length > 160) errors.desired_title = 'Бажана посада — до 160 символів.';
  const years = yearsText === '' ? null : Number(yearsText);
  if (years !== null && (!/^\d+$/.test(yearsText) || years > 70)) errors.years = 'Вкажіть ціле число років від 0 до 70.';
  if (location.length > 120) errors.location = 'Локація — до 120 символів.';
  if (Object.keys(errors).length) return { errors, body: null };
  return { errors, body: { name, track: f.track, desired_title: title, years_experience: years, location } };
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
