import { BarChart3, Briefcase, Home, MessageSquareText, PieChart, UserRound, type LucideIcon } from 'lucide-react';

export type StepKey = 'welcome' | 'profile' | 'interview' | 'results' | 'vacancies' | 'market';

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
  { n: 5, key: 'vacancies', label: 'Вакансії', short: 'Вакансії', icon: Briefcase },
  { n: 6, key: 'market', label: 'Профіль ринку', short: 'Ринок', icon: PieChart },
];

/** Steps shown in the mobile bottom tab bar (the full stepper lives in the menu drawer). */
export const MOBILE_TAB_KEYS: readonly StepKey[] = ['welcome', 'interview', 'results', 'vacancies', 'market'];

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
    : pathname === '/vacancies' || pathname.startsWith('/vacancies/') ? 'vacancies'
    : pathname === '/market' ? 'market'
    : null;
  return STEPS.find((s) => s.key === key) ?? null;
}

/** Title for the step header strip and `document.title`. */
export function pageTitleFor(pathname: string): string {
  if (pathname === '/login') return 'Вхід';
  if (pathname === '/profiles') return 'Профілі';
  return stepForPath(pathname)?.label ?? 'Сторінку не знайдено';
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
    stage === 'finished' ? ['welcome', 'profile', 'interview']
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
        if (stage === 'none') to = '/profile';
        else reason = 'Профіль зафіксовано для поточної співбесіди';
        break;
      case 'interview':
        if (stage === 'active' && interview) to = `/interview/${interview.id}`;
        else reason = stage === 'finished' ? 'Співбесіду завершено' : 'Спершу заповніть профіль';
        break;
      case 'vacancies':
        to = '/vacancies';
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
 * Resolve the landing path after boot. A deep link (anything other than `/`) is kept;
 * the bare root resumes the candidate's current stage like the pre-router app did.
 */
export function landingPath(requested: string, interview: SessionInterview | null): string {
  return requested === '/' ? resumePath(interview) : requested;
}
