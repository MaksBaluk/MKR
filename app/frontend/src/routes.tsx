import { lazy, useEffect, useState, type ReactNode } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { Compass, Loader2, RefreshCw, UsersRound } from 'lucide-react';
import { api } from '@/api';
import { AppShell, SkipLink } from '@/components/AppShell';
import { ErrorRetry } from '@/components/ErrorRetry';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { ActiveProfileProvider, useActiveProfile } from '@/lib/activeProfile';
import { useProfileInterview } from '@/hooks/useProfileInterview';
import { isProfileComplete } from '@/lib/profiles';
import { landingAfterAuth, safeReturnPath } from '@/lib/navigation';
import { AuthScreen } from '@/screens/AuthScreen';
import { InterviewScreen } from '@/screens/InterviewScreen';
import { ProfileHubPage } from '@/screens/ProfileHub';
import { SettingsScreen } from '@/screens/SettingsScreen';
import { WelcomeScreen } from '@/screens/WelcomeScreen';
import { MarketScreen } from '@/screens/MarketScreen';
import { ResultsScreen } from '@/screens/ResultsScreen';
import type { CandidateProfile } from '@/types';
import { useSession } from '@/session';

// Catalogue and profile management are separate chunks; a failed download is caught by the shell's ErrorBoundary.
const VacanciesScreen = lazy(() => import('@/screens/VacanciesScreen').then((m) => ({ default: m.VacanciesScreen })));
const VacancyDetail = lazy(() => import('@/screens/VacancyDetail').then((m) => ({ default: m.VacancyDetail })));
const ProfilesScreen = lazy(() => import('@/screens/ProfilesScreen').then((m) => ({ default: m.ProfilesScreen })));

function FullScreenLoader() {
  return (
    <div className="flex min-h-dvh items-center justify-center gap-2 text-ink-muted" role="status">
      <Loader2 className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
      Завантаження…
    </div>
  );
}

function BootError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center p-4">
      <Card className="flex flex-col gap-4 p-6">
        <h1 className="text-lg font-semibold text-ink">Не вдалося відкрити застосунок</h1>
        <Alert role="alert" variant="danger">{message}</Alert>
        <Button onClick={onRetry} className="self-start">
          <RefreshCw className="size-4" aria-hidden="true" />
          Спробувати ще раз
        </Button>
      </Card>
    </main>
  );
}

function LoginPage() {
  const { status, boot, sessionExpired } = useSession();
  const location = useLocation();
  // After sign-in land on welcome/profile, never straight in an interview (resume is a button there).
  const [kind, setKind] = useState<'login' | 'register'>('login');
  const from = landingAfterAuth(kind, safeReturnPath((location.state as { from?: unknown } | null)?.from));
  useEffect(() => {
    document.title = 'Вхід · CompetenceMatch';
  }, []);
  if (status === 'ready') return <Navigate to={from} replace />;
  if (status === 'loading') return <FullScreenLoader />;
  return (
    <>
      <SkipLink />
      <AuthScreen onSignedIn={(k) => { setKind(k); void boot(); }} notice={sessionExpired ? 'Сесію завершено. Увійдіть знову.' : null} />
    </>
  );
}

/** App shell whose stepper, locks and banners follow the active candidate profile. */
function ShellForActiveProfile({ name, email, onLogout }: { name: string; email: string; onLogout: () => void }) {
  const interview = useProfileInterview();
  const { active } = useActiveProfile();
  return <AppShell name={name} email={email} interview={interview} profileComplete={isProfileComplete(active)} onLogout={onLogout} />;
}

/** Guard + shell for every signed-in route. Resumes the candidate's stage once after boot. */
function AuthenticatedLayout() {
  const session = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const { status, justBooted, consumeBoot } = session;

  useEffect(() => {
    if (status !== 'ready' || !justBooted) return;
    consumeBoot(); // boot keeps the current URL: the root stays on the welcome step, deep links stay put
  }, [status, justBooted, consumeBoot]);

  if (status === 'loading') return <FullScreenLoader />;
  if (status === 'error') return <BootError message={session.error ?? 'Не вдалося завантажити дані.'} onRetry={() => void session.boot()} />;
  if (status === 'anonymous' || !session.profile)
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  return (
    <ActiveProfileProvider>
      <ShellForActiveProfile name={session.profile.display_name} email={session.profile.email}
        onLogout={() => { session.signOut(); navigate('/login', { replace: true }); }} />
    </ActiveProfileProvider>
  );
}

/**
 * Candidate profile that owns an attempt. The interview API does not return the profile id, so the
 * attempt lists are checked (active profile first; users have few profiles). Null while unknown.
 */
function useAttemptOwner(interviewId: string): CandidateProfile | null {
  const { profiles, active } = useActiveProfile();
  const [owner, setOwner] = useState<CandidateProfile | null>(null);
  useEffect(() => {
    let live = true;
    const ordered = active ? [active, ...profiles.filter((p) => p.id !== active.id)] : profiles;
    (async () => {
      for (const p of ordered.filter((x) => x.attempts_count > 0)) {
        try {
          const r = await api<{ items: { id: string }[] }>(`/profiles/${encodeURIComponent(p.id)}/attempts`);
          if (r.items.some((a) => a.id === interviewId)) {
            if (live) setOwner(p);
            return;
          }
        } catch {
          return;
        }
      }
    })();
    return () => {
      live = false;
    };
  }, [interviewId, profiles, active]);
  return owner;
}

function InterviewPage() {
  const { id = '' } = useParams();
  const { profile, llmConfigured, refreshInterview } = useSession();
  const { reload } = useActiveProfile();
  const owner = useAttemptOwner(id);
  const navigate = useNavigate();
  if (!profile) return null;
  // Header shows the attempt's own profile (title/track) once known; the account profile until then.
  const shown = owner ? { ...profile, desired_title: owner.desired_title, track: owner.track ?? profile.track } : profile;
  return (
    <InterviewScreen key={id} interviewId={id} profile={shown} llmConfigured={llmConfigured}
      onFinished={() => {
        void Promise.all([refreshInterview().catch(() => null), reload()]).finally(() => navigate('/results', { replace: true }));
      }} />
  );
}

/** Step 2. Only before the first interview: the profile is frozen into the interview snapshot afterwards. */
/** Resolves the active candidate profile, then renders the page for it. */
function WithActiveProfile({ render }: { render: (p: CandidateProfile) => ReactNode }) {
  const { status, active, error, reload } = useActiveProfile();
  if (status === 'loading')
    return (
      <div aria-busy="true">
        <p role="status" className="sr-only">Завантаження профілю…</p>
        <Skeleton className="h-40" />
      </div>
    );
  if (status === 'error')
    return (
      <ErrorRetry message={error} onRetry={() => void reload()} />
    );
  if (!active)
    return (
      <EmptyState icon={UsersRound} title="Профілю ще немає"
        action={<Button asChild><Link to="/profile">Заповнити профіль</Link></Button>}>
        Створіть профіль кандидата, щоб пройти співбесіду й побачити результати.
      </EmptyState>
    );
  return <>{render(active)}</>;
}

function ResultsPage() {
  const interview = useProfileInterview();
  return (
    <div className="flex flex-col gap-4">
      {interview?.status === 'active' && (
        <Alert role="note" variant="info" className="flex flex-wrap items-center justify-between gap-3">
          <span>У вас є незавершена співбесіда. Нові результати з’являться після її завершення.</span>
          <Button asChild size="sm" variant="outline"><Link to={`/interview/${interview.id}`}>Продовжити розмову</Link></Button>
        </Alert>
      )}
      <WithActiveProfile render={(p) => <ResultsScreen key={p.id} profile={p} />} />
    </div>
  );
}

function NotFoundPage() {
  return (
    <EmptyState icon={Compass} title="Такої сторінки немає"
      action={<Button asChild><Link to="/">На головну</Link></Button>}>
      Можливо, посилання застаріло або в адресі є помилка.
    </EmptyState>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthenticatedLayout />}>
        <Route index element={<WelcomeScreen />} />
        <Route path="profile" element={<ProfileHubPage />} />
        <Route path="profiles" element={<ProfilesScreen />} />
        <Route path="settings" element={<SettingsScreen />} />
        <Route path="vacancies" element={<VacanciesScreen />} />
        <Route path="vacancies/:id" element={<VacancyDetail />} />
        <Route path="market" element={<WithActiveProfile render={(p) => <MarketScreen key={p.id} profile={p} />} />} />
        <Route path="results" element={<ResultsPage />} />
        <Route path="interview/:id" element={<InterviewPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
