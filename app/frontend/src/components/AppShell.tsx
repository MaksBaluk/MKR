import { Suspense, useEffect, useId, useRef, useState, type RefObject } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { Check, ChevronDown, Lock, LogOut, Menu, Settings2, UserRound, UsersRound } from 'lucide-react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Avatar } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';
import { useActiveProfile } from '@/lib/activeProfile';
import { trackLabel } from '@/lib/profiles';
import { Dialog } from '@/components/ui/dialog';
import {
  MOBILE_TAB_KEYS, STEPS, isFocusLayout, pageTitleFor, stepForPath, stepStates,
  type SessionInterview, type StepState,
} from '@/lib/navigation';
import { cn } from '@/lib/utils';

const focusRing = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring';
const DESKTOP = '(min-width: 1024px)';

export function Logo({ compact = false, inverted = false }: { compact?: boolean; inverted?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <span aria-hidden="true" className={cn('relative flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-xl shadow-sm',
        inverted ? 'bg-white/15 ring-1 ring-white/25' : 'bg-gradient-to-br from-primary to-brand-deep')}>
        <svg viewBox="0 0 24 24" className="size-6" fill="none" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 17 8.5 7l4 7 3-5L21 17" stroke="white" />
          <path d="m12.5 14 3-5L21 17" stroke={inverted ? '#99f6e4' : '#5eead4'} />
        </svg>
      </span>
      <span className={cn('text-lg font-bold tracking-tight', compact && 'sr-only', inverted ? 'text-white' : 'text-ink')}>
        Competence<span className={inverted ? 'text-blue-100' : 'text-primary'}>Match</span>
      </span>
    </span>
  );
}

export function SkipLink() {
  return (
    <a href="#main-content"
      className="sr-only z-50 rounded-xl bg-primary px-4 py-3 font-semibold text-on-primary focus:not-sr-only focus:fixed focus:top-3 focus:left-3">
      Перейти до основного вмісту
    </a>
  );
}

function StepCircle({ s }: { s: StepState }) {
  return (
    <span aria-hidden="true" className={cn('relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ring-4 ring-surface',
      s.status === 'current' ? 'bg-primary text-on-primary'
      : s.status === 'done' ? 'bg-accent text-white'
      : s.status === 'available' ? 'border border-line-strong bg-surface text-ink-muted'
      : 'border border-line bg-surface-muted text-ink-subtle')}>
      {s.status === 'done' ? <Check className="size-4" strokeWidth={3} /> : s.step.n}
    </span>
  );
}

const STATUS_TEXT = { current: 'поточний крок', done: 'виконано', available: '', locked: 'недоступно' } as const;

/** Numbered vertical stepper used as primary navigation (sidebar and mobile drawer). */
function StepperNav({ states, collapsed = false, onNavigate }: { states: StepState[]; collapsed?: boolean; onNavigate?: () => void }) {
  const reasonBase = useId();
  return (
    <ol className="flex flex-col gap-1">
      {states.map((s, i) => {
        const last = i === states.length - 1;
        const inner = (
          <>
            <StepCircle s={s} />
            <s.step.icon className={cn('size-5 shrink-0', collapsed && 'hidden',
              s.status === 'current' ? 'text-primary' : s.status === 'locked' ? 'text-ink-subtle/70' : 'text-ink-subtle')} aria-hidden="true" />
            <span className={cn('min-w-0 flex-1 truncate', collapsed && 'sr-only')}>
              {s.step.label}
              {STATUS_TEXT[s.status] && <span className="sr-only">, {STATUS_TEXT[s.status]}</span>}
            </span>
            {s.status === 'locked' && !collapsed && <Lock className="size-3.5 shrink-0 text-ink-subtle/70" aria-hidden="true" />}
          </>
        );
        const base = cn('relative flex min-h-12 items-center gap-3 rounded-xl px-2.5 text-sm font-medium transition-colors duration-150 motion-reduce:transition-none',
          focusRing, collapsed && 'justify-center px-0');
        return (
          <li key={s.step.key} className="relative">
            {!last && (
              <span aria-hidden="true" className={cn('absolute top-9 bottom-[-0.75rem] w-px',
                collapsed ? 'left-1/2' : 'left-[1.5rem]', s.status === 'done' ? 'bg-accent/50' : 'bg-line-strong')} />
            )}
            {s.to && s.status !== 'locked' ? (
              <Link to={s.to} onClick={onNavigate} aria-current={s.status === 'current' ? 'page' : undefined}
                title={collapsed ? s.step.label : undefined}
                className={cn(base, s.status === 'current' ? 'bg-primary-soft text-primary-strong' : 'text-ink hover:bg-surface-muted')}>
                {inner}
              </Link>
            ) : (
              // Not openable now: visible, focusable for screen-reader discovery, explained via title + description.
              <span role="link" aria-disabled="true" tabIndex={0} title={s.reason ?? undefined}
                aria-current={s.status === 'current' ? 'page' : undefined}
                aria-describedby={s.reason ? `${reasonBase}-${s.step.key}` : undefined}
                className={cn(base, 'cursor-not-allowed', s.status === 'current' ? 'bg-primary-soft text-primary-strong' : 'text-ink-subtle')}>
                {inner}
                {s.reason && <span id={`${reasonBase}-${s.step.key}`} className="sr-only">{s.reason}</span>}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** Open/close behaviour shared by the top-bar menus: closes on navigation, outside click and Esc (focus returns). */
function useMenu(ref: RefObject<HTMLDivElement | null>) {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        ref.current?.querySelector<HTMLButtonElement>('button')?.focus();
      }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, ref]);
  return [open, setOpen] as const;
}

const menuItem = cn('flex min-h-11 w-full cursor-pointer items-center gap-3 rounded-xl px-3 text-left text-sm font-medium text-ink hover:bg-surface-muted', focusRing);

/** Active candidate profile switcher; changing it re-scopes results, market and the vacancy CTA app-wide. */
function ProfileSwitcher() {
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useMenu(ref);
  const menuId = useId();
  const { profiles, active, setActive, status } = useActiveProfile();
  if (status !== 'ready' || profiles.length === 0) return null;
  return (
    <div ref={ref} className="relative min-w-0">
      <button type="button" aria-expanded={open} aria-controls={menuId} onClick={() => setOpen((v) => !v)}
        aria-label={`Активний профіль: ${active?.name ?? 'не вибрано'}. Змінити профіль`}
        className={cn('flex min-h-11 max-w-44 min-w-0 cursor-pointer items-center gap-2 rounded-xl border border-line px-2.5 hover:bg-surface-muted sm:max-w-64', focusRing)}>
        <UserRound className="size-4 shrink-0 text-primary" aria-hidden="true" />
        <span className="min-w-0 truncate text-sm font-medium text-ink">{active?.name ?? 'Профіль'}</span>
        <ChevronDown className={cn('size-4 shrink-0 text-ink-subtle transition-transform motion-reduce:transition-none', open && 'rotate-180')} aria-hidden="true" />
      </button>
      <div id={menuId} hidden={!open}
        className="absolute top-full right-0 z-40 mt-2 w-72 max-w-[calc(100vw-1rem)] rounded-2xl border border-line bg-surface p-2 shadow-raised">
        <p className="px-3 pt-1 pb-2 text-xs font-medium text-ink-subtle">Активний профіль</p>
        <ul>
          {profiles.map((p) => {
            const current = p.id === active?.id;
            return (
              <li key={p.id}>
                <button type="button" aria-pressed={current} onClick={() => { setActive(p.id); setOpen(false); }} className={menuItem}>
                  <Check className={cn('size-4 shrink-0 text-primary', !current && 'invisible')} aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{p.name}</span>
                    <span className="block truncate text-xs font-normal text-ink-subtle">{trackLabel(p.track)}</span>
                  </span>
                </button>
              </li>
            );
          })}
          <li className="mt-1 border-t border-line pt-1">
            <Link to="/profiles" className={menuItem}>
              <Settings2 className="size-4 text-ink-subtle" aria-hidden="true" />Керувати профілями
            </Link>
          </li>
        </ul>
      </div>
    </div>
  );
}

function UserMenu({ name, email, onLogout }: { name: string; email: string; onLogout: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useMenu(ref);
  const menuId = useId();

  const item = menuItem;
  return (
    <div ref={ref} className="relative">
      <button type="button" aria-expanded={open} aria-controls={menuId} onClick={() => setOpen((v) => !v)}
        aria-label={`Меню користувача: ${name || 'Кандидат'}`}
        className={cn('flex min-h-11 cursor-pointer items-center gap-2 rounded-xl py-1 pr-2 pl-1 hover:bg-surface-muted', focusRing)}>
        <Avatar name={name} className="size-9" />
        <span className="hidden max-w-40 truncate text-sm font-semibold text-ink sm:block">{name || 'Кандидат'}</span>
        <ChevronDown className={cn('size-4 text-ink-subtle transition-transform motion-reduce:transition-none', open && 'rotate-180')} aria-hidden="true" />
      </button>
      <div id={menuId} hidden={!open}
        className="absolute top-full right-0 z-40 mt-2 w-64 rounded-2xl border border-line bg-surface p-2 shadow-raised">
        <div className="border-b border-line px-3 pt-1 pb-3">
          <p className="truncate text-sm font-semibold text-ink">{name || 'Кандидат'}</p>
          <p className="truncate text-xs text-ink-subtle">{email}</p>
        </div>
        <ul className="pt-2">
          <li>
            <Link to="/profiles" className={item}>
              <UsersRound className="size-4 text-ink-subtle" aria-hidden="true" />
              Профілі
            </Link>
          </li>
          <li>
            <button type="button" onClick={onLogout} className={cn(item, 'text-danger-ink hover:bg-danger-soft')}>
              <LogOut className="size-4" aria-hidden="true" />
              Вийти
            </button>
          </li>
        </ul>
      </div>
    </div>
  );
}

/** Authenticated layout: stepper sidebar (>=1024px) or drawer + bottom tab bar (<1024px), top bar, step header strip. */
export function AppShell({ name, email, interview, onLogout }: {
  name: string;
  email: string;
  interview: SessionInterview | null;
  onLogout: () => void;
}) {
  const { pathname } = useLocation();
  const focus = isFocusLayout(pathname);
  const title = pageTitleFor(pathname);
  const step = stepForPath(pathname);
  const states = stepStates(pathname, interview);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    document.title = `${title} · CompetenceMatch`;
    setDrawer(false);
    // Move focus to the page heading on client-side navigation (not on first load).
    if (firstRender.current) firstRender.current = false;
    else headingRef.current?.focus();
  }, [pathname, title]);

  function toggleMenu() {
    if (window.matchMedia(DESKTOP).matches) setCollapsed((v) => !v);
    else setDrawer(true);
  }

  return (
    <div className={cn('min-h-dvh lg:grid', collapsed ? 'lg:grid-cols-[5rem_minmax(0,1fr)]' : 'lg:grid-cols-[17.5rem_minmax(0,1fr)]')}>
      <SkipLink />

      <aside aria-label="Етапи оцінювання" className="sticky top-0 hidden h-dvh flex-col border-r border-line bg-surface lg:flex">
        <div className={cn('flex h-16 shrink-0 items-center border-b border-line', collapsed ? 'justify-center' : 'px-5')}>
          <Link to="/" className={cn('rounded-xl', focusRing)} aria-label="CompetenceMatch — до вітання">
            <Logo compact={collapsed} />
          </Link>
        </div>
        <nav aria-label="Кроки оцінювання" className="flex-1 overflow-y-auto px-3 py-5">
          <StepperNav states={states} collapsed={collapsed} />
        </nav>
        {!collapsed && (
          <p className="border-t border-line px-5 py-4 text-xs leading-relaxed text-ink-subtle">
            Вакансії в каталозі синтетичні й не є актуальними пропозиціями роботодавців.
          </p>
        )}
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
          <div className="flex h-16 items-center gap-2 px-2 sm:px-4 lg:px-6">
            <button type="button" onClick={toggleMenu} aria-label="Меню кроків"
              className={cn('flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-xl text-ink-muted hover:bg-surface-muted hover:text-ink', focusRing)}>
              <Menu className="size-5" aria-hidden="true" />
            </button>
            <Link to="/" className={cn('rounded-xl lg:hidden', focusRing)} aria-label="CompetenceMatch — до вітання">
              <Logo compact />
            </Link>
            <p className="ml-1 hidden min-w-0 flex-1 truncate text-base font-semibold text-ink sm:block">Оцінювання компетентностей</p>
            <span className="flex-1 sm:hidden" />
            <ProfileSwitcher />
            <span aria-hidden="true" className="mx-1 hidden h-8 w-px bg-line sm:block" />
            <UserMenu name={name} email={email} onLogout={onLogout} />
          </div>
        </header>

        <div className="border-b border-line bg-surface/60 px-4 py-4 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-6xl flex-col gap-2.5">
            <div className="flex items-baseline justify-between gap-3">
              <h1 ref={headingRef} tabIndex={-1} id="page-title" className="min-w-0 text-base font-bold tracking-tight text-ink sm:text-lg">
                {step ? <><span className="text-ink-muted">Крок {step.n} із {STEPS.length}:</span> {title}</> : title}
              </h1>
              {step && <span className="shrink-0 text-sm font-medium tabular-nums text-ink-muted" aria-hidden="true">{step.n} із {STEPS.length}</span>}
            </div>
            {step && (
              <div className="h-2 overflow-hidden rounded-full bg-primary-soft" aria-hidden="true">
                <div className="h-full rounded-full bg-primary transition-[width] duration-500 motion-reduce:transition-none"
                  style={{ width: `${(step.n / STEPS.length) * 100}%` }} />
              </div>
            )}
          </div>
        </div>

        <main id="main-content" tabIndex={-1} aria-labelledby="page-title"
          className={cn('flex-1 px-4 py-5 sm:px-6 sm:py-6 lg:px-8 lg:pb-10',
            focus ? 'pb-[calc(1.25rem+env(safe-area-inset-bottom))]' : 'pb-[calc(6rem+env(safe-area-inset-bottom))]')}>
          <div className="mx-auto w-full max-w-6xl">
            <ErrorBoundary resetKey={pathname}>
              <Suspense fallback={
                <div aria-busy="true"><p role="status" className="sr-only">Завантаження сторінки…</p><Skeleton className="h-64" /></div>
              }>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </div>
        </main>
      </div>

      <Dialog open={drawer} onClose={() => setDrawer(false)} title="Кроки оцінювання" side="left" className="lg:hidden">
        <nav aria-label="Кроки оцінювання">
          <StepperNav states={states} onNavigate={() => setDrawer(false)} />
        </nav>
        <p className="mt-6 text-xs leading-relaxed text-ink-subtle">Вакансії в каталозі синтетичні й не є актуальними пропозиціями роботодавців.</p>
      </Dialog>

      {!focus && (
        <nav aria-label="Основні кроки"
          className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] shadow-nav backdrop-blur lg:hidden">
          <ul className="mx-auto grid max-w-lg grid-cols-5">
            {states.filter((s) => MOBILE_TAB_KEYS.includes(s.step.key)).map((s) => {
              const active = s.status === 'current';
              const cls = cn('flex min-h-16 flex-col items-center justify-center gap-1 px-0.5 text-xs font-medium -outline-offset-2', focusRing);
              const icon = (
                <span className={cn('flex h-7 w-11 items-center justify-center rounded-full transition-colors motion-reduce:transition-none', active && 'bg-primary-soft')}>
                  <s.step.icon className="size-5" aria-hidden="true" />
                </span>
              );
              return (
                <li key={s.step.key}>
                  {s.to && s.status !== 'locked' ? (
                    <Link to={s.to} aria-current={active ? 'page' : undefined}
                      className={cn(cls, active ? 'text-primary-strong' : 'text-ink-muted hover:text-ink')}>
                      {icon}
                      <span className="max-w-full truncate">{s.step.short}</span>
                    </Link>
                  ) : (
                    <span role="link" aria-disabled="true" tabIndex={0} title={s.reason ?? undefined}
                      aria-current={active ? 'page' : undefined}
                      className={cn(cls, active ? 'text-primary-strong' : 'text-ink-subtle/80')}>
                      {icon}
                      <span className="max-w-full truncate">{s.step.short}</span>
                      {s.reason && <span className="sr-only">: {s.reason}</span>}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </div>
  );
}
