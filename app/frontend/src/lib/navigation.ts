import { BarChart3, Briefcase, Home, MessageSquareText, PieChart, Settings2, UserRound, type LucideIcon } from 'lucide-react';

export type StepKey = 'welcome' | 'profile' | 'interview' | 'results' | 'market';
export type SideKey = 'vacancies' | 'settings';

export interface Step {
  n: number;
  key: StepKey;
  label: string;
  /** Short label for the mobile tab bar. */
  short: string;
  icon: LucideIcon;
}

/** The candidate journey shown as a numbered stepper (sidebar) and the step header strip. */
export const STEPS: readonly Step[] = [
  { n: 1, key: 'welcome', label: 'Вітання', short: 'Вітання', icon: Home },
  { n: 2, key: 'profile', label: 'Профіль', short: 'Профіль', icon: UserRound },
  { n: 3, key: 'interview', label: 'Інтерв’ю', short: 'Інтерв’ю', icon: MessageSquareText },
  { n: 4, key: 'results', label: 'Результати', short: 'Результати', icon: BarChart3 },
  { n: 5, key: 'market', label: 'Профіль ринку', short: 'Ринок', icon: PieChart },
];

export interface SideItem {
  key: SideKey;
  label: string;
  short: string;
  to: string;
  icon: LucideIcon;
}

/** Outside the journey stepper: never locked, reachable at any stage. */
export const SIDE_ITEMS: readonly SideItem[] = [
  { key: 'vacancies', label: 'Вакансії', short: 'Вакансії', to: '/vacancies', icon: Briefcase },
  { key: 'settings', label: 'Налаштування', short: 'Налаштування', to: '/settings', icon: Settings2 },
];

/** Order of the mobile bottom tab bar (five tabs). */
export const MOBILE_TAB_KEYS: readonly (StepKey | SideKey)[] = ['welcome', 'interview', 'results', 'vacancies', 'market'];

export interface SessionInterview {
  id: string;
  cohort_id: string;
  status: 'active' | 'finished';
}

export function stepForPath(pathname: string): Step | null {
  const key: StepKey | null =
    pathname === '/' ? 'welcome'
    : pathname === '/profile' ? 'profile'
    : pathname.startsWith('/interview/') ? 'interview'
    : pathname === '/results' ? 'results'
    : pathname === '/market' ? 'market'
    : null;
  return STEPS.find((s) => s.key === key) ?? null;
}

/** Side item for a path (vacancies and nested vacancy pages, settings), or null. */
export function sideForPath(pathname: string): SideItem | null {
  if (pathname === '/vacancies' || pathname.startsWith('/vacancies/')) return SIDE_ITEMS[0];
  if (pathname === '/settings') return SIDE_ITEMS[1];
  return null;
}

/** Title for the step header strip and `document.title`. */
export function pageTitleFor(pathname: string): string {
  if (pathname === '/login') return 'Вхід';
  if (pathname === '/profiles') return 'Профілі';
  return stepForPath(pathname)?.label ?? sideForPath(pathname)?.label ?? 'Сторінку не знайдено';
}

export type StepStatus = 'current' | 'done' | 'available' | 'locked';

export interface StepState {
  step: Step;
  /** Route to open, or null when the step cannot be opened now. */
  to: string | null;
  status: StepStatus;
  /** Why the step is not clickable (tooltip + accessible description). */
  reason: string | null;
}

const AFTER_INTERVIEW = 'Доступно після завершення співбесіди';

/**
 * Availability of each journey step for the candidate's current stage.
 * The vacancy catalogue is browsable at any time (it is not a job choice: the cohort is still system-selected);
 * results and the market profile open only after the interview is finished.
 */
export function stepStates(pathname: string, interview: SessionInterview | null): StepState[] {
  const current = stepForPath(pathname)?.key ?? null;
  const stage = interview?.status ?? 'none';
  const done = new Set<StepKey>(
    stage === 'finished' ? ['welcome', 'profile', 'interview', 'results', 'market']
    : stage === 'active' ? ['welcome', 'profile']
    : current === 'profile' ? ['welcome']
    : [],
  );
  return STEPS.map((step) => {
    let to: string | null = null;
    let reason: string | null = null;
    switch (step.key) {
      case 'welcome':
        to = '/';
        break;
      case 'profile':
        to = '/profile'; // always reachable, also while an interview is open or finished
        break;
      case 'interview':
        if (stage === 'active' && interview) to = `/interview/${interview.id}`;
        else reason = stage === 'finished' ? 'Співбесіду завершено' : 'Спершу заповніть профіль';
        break;
      default:
        if (stage === 'finished') to = `/${step.key}`;
        else reason = AFTER_INTERVIEW;
    }
    const status: StepStatus =
      step.key === current ? 'current' : done.has(step.key) ? 'done' : to ? 'available' : 'locked';
    return { step, to: status === 'current' ? to ?? pathname : to, status, reason: status === 'current' ? null : reason };
  });
}

export interface SideState {
  key: SideKey;
  label: string;
  short: string;
  icon: LucideIcon;
  to: string;
  status: 'current' | 'available';
}

/** Side items for the current path. They are never locked. */
export function sideStates(pathname: string): SideState[] {
  const current = sideForPath(pathname)?.key ?? null;
  return SIDE_ITEMS.map((item) => ({
    key: item.key, label: item.label, short: item.short, icon: item.icon, to: item.to,
    status: item.key === current ? 'current' : 'available',
  }));
}

/** One entry of the mobile bottom tab bar: a journey step or a side item, with the same availability rules. */
export interface MobileTab {
  key: StepKey | SideKey;
  short: string;
  icon: LucideIcon;
  to: string | null;
  status: StepStatus | 'available';
  reason: string | null;
}

export function mobileTabs(pathname: string, interview: SessionInterview | null): MobileTab[] {
  const steps = new Map(stepStates(pathname, interview).map((s) => [s.step.key, s]));
  const side = new Map(sideStates(pathname).map((s) => [s.key, s]));
  return MOBILE_TAB_KEYS.map((key) => {
    const st = steps.get(key as StepKey);
    if (st) return { key, short: st.step.short, icon: st.step.icon, to: st.to, status: st.status, reason: st.reason };
    const sd = side.get(key as SideKey)!;
    return { key, short: sd.short, icon: sd.icon, to: sd.to, status: sd.status, reason: null };
  });
}

/** True for the focused interview layout (no bottom tab bar on phones, more room for the chat). */
export function isFocusLayout(pathname: string): boolean {
  return pathname.startsWith('/interview/');
}

/**
 * Sanitises a post-login return path. Only same-origin app paths are allowed;
 * protocol-relative (`//evil`) and `/login` itself fall back to `/`.
 */
export function safeReturnPath(from: unknown): string {
  if (typeof from !== 'string' || !from.startsWith('/') || from.startsWith('//') || from.startsWith('/\\')) return '/';
  if (from === '/login' || from.startsWith('/login?')) return '/';
  return from;
}

/** Where the app resumes after boot: open interview, finished results, or onboarding. */
export function resumePath(interview: SessionInterview | null): string {
  if (interview?.status === 'active') return `/interview/${interview.id}`;
  if (interview?.status === 'finished') return '/results';
  return '/';
}

/**
 * Where to land after sign-in. Never drops the candidate straight into an interview:
 * an interview return path falls back to the welcome step, which offers «Продовжити співбесіду»
 * (via `resumePath`). Other app paths are kept.
 */
export function landingPath(requested: string): string {
  return requested.startsWith('/interview/') ? '/' : requested;
}

/**
 * Steps reached so far, from the profile's state only (never from the open page, so visiting «Вітання» cannot
 * shrink it): welcome, a complete profile, an open interview, a finished one (results and market are open).
 */
export function progressSteps(interview: SessionInterview | null, profileComplete: boolean): number {
  if (interview?.status === 'finished') return STEPS.length;
  if (interview?.status === 'active') return 3;
  return profileComplete ? 2 : 1;
}

export function progressPercent(interview: SessionInterview | null, profileComplete: boolean): number {
  return Math.round((progressSteps(interview, profileComplete) / STEPS.length) * 100);
}

/** Where to land after authentication: a new account starts on the welcome page, sign-in keeps the safe target. */
export function landingAfterAuth(kind: 'login' | 'register', requested: string): string {
  return kind === 'register' ? '/' : landingPath(requested);
}
