import { useEffect, type ReactNode } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { BarChart3, Briefcase, Compass, Construction, Loader2, MessageSquare, RefreshCw, UsersRound } from 'lucide-react';
import { AppShell, SkipLink } from '@/components/AppShell';
import { ErrorRetry } from '@/components/ErrorRetry';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { ActiveProfileProvider, useActiveProfile } from '@/lib/activeProfile';
import { landingPath, safeReturnPath } from '@/lib/navigation';
import { AuthScreen } from '@/screens/AuthScreen';
import { InterviewScreen } from '@/screens/InterviewScreen';
import { ProfileScreen } from '@/screens/ProfileScreen';
import { WelcomeScreen } from '@/screens/WelcomeScreen';
import { MarketScreen } from '@/screens/MarketScreen';
import { ResultsScreen } from '@/screens/ResultsScreen';
import type { CandidateProfile } from '@/types';
import { useSession } from '@/session';

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
  const from = safeReturnPath((location.state as { from?: unknown } | null)?.from);
  useEffect(() => {
    document.title = 'Вхід · CompetenceMatch';
  }, []);
  if (status === 'ready') return <Navigate to={from} replace />;
  if (status === 'loading') return <FullScreenLoader />;
  return (
    <>
      <SkipLink />
      <AuthScreen onSignedIn={() => void boot()} notice={sessionExpired ? 'Сесію завершено. Увійдіть знову.' : null} />
    </>
  );
}

/** Guard + shell for every signed-in route. Resumes the candidate's stage once after boot. */
function AuthenticatedLayout() {
  const session = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const { status, justBooted, consumeBoot, interview } = session;

  useEffect(() => {
    if (status !== 'ready' || !justBooted) return;
    consumeBoot();
    const target = landingPath(location.pathname, interview);
    if (target !== location.pathname) navigate(target, { replace: true });
  }, [status, justBooted, consumeBoot, interview, location.pathname, navigate]);

  if (status === 'loading') return <FullScreenLoader />;
  if (status === 'error') return <BootError message={session.error ?? 'Не вдалося завантажити дані.'} onRetry={() => void session.boot()} />;
  if (status === 'anonymous' || !session.profile)
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  return (
    <ActiveProfileProvider>
      <AppShell name={session.profile.display_name} email={session.profile.email} interview={session.interview}
        onLogout={() => { session.signOut(); navigate('/login', { replace: true }); }} />
    </ActiveProfileProvider>
  );
}

function InterviewPage() {
  const { id = '' } = useParams();
  const { profile, llmConfigured, refreshInterview } = useSession();
  const navigate = useNavigate();
  if (!profile) return null;
  return (
    <InterviewScreen key={id} interviewId={id} profile={profile} llmConfigured={llmConfigured}
      onFinished={() => {
        void refreshInterview().finally(() => navigate('/results', { replace: true }));
      }} />
  );
}

/** Step 2. Only before the first interview: the profile is frozen into the interview snapshot afterwards. */
function ProfilePage() {
  const { profile, interview, setProfile, refreshInterview } = useSession();
  const navigate = useNavigate();
  if (!profile) return null;
  if (interview?.status === 'active')
    return (
      <EmptyState icon={MessageSquare} title="Профіль уже використано в розмові"
        action={<Button asChild><Link to={`/interview/${interview.id}`}>Продовжити розмову</Link></Button>}>
        Дані профілю зафіксовано для поточної співбесіди. Самооцінку можна змінити в результатах.
      </EmptyState>
    );
  if (interview?.status === 'finished')
    return (
      <EmptyState icon={BarChart3} title="Співбесіду завершено"
        action={<Button asChild><Link to="/results">До результатів</Link></Button>}>
        Профіль зафіксовано разом із результатами. Самооцінку можна змінити на вкладці «Мій профіль» у результатах.
      </EmptyState>
    );
  return (
    <ProfileScreen profile={profile} onSaved={setProfile}
      onStarted={(id) => {
        void refreshInterview().finally(() => navigate(`/interview/${id}`));
      }} />
  );
}

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
  const { interview } = useSession();
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

function ComingSoonPage({ section, icon }: { section: string; icon: typeof Construction }) {
  return (
    <EmptyState icon={icon} title="Розділ у розробці"
      action={<Button asChild variant="outline"><Link to="/">На головну</Link></Button>}>
      Розділ «{section}» з’явиться найближчим часом.
    </EmptyState>
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
        <Route path="profile" element={<ProfilePage />} />
        <Route path="profiles" element={<ComingSoonPage section="Профілі" icon={UsersRound} />} />
        <Route path="vacancies" element={<ComingSoonPage section="Вакансії" icon={Briefcase} />} />
        <Route path="vacancies/:id" element={<ComingSoonPage section="Деталі вакансії" icon={Briefcase} />} />
        <Route path="market" element={<WithActiveProfile render={(p) => <MarketScreen key={p.id} profile={p} />} />} />
        <Route path="results" element={<ResultsPage />} />
        <Route path="interview/:id" element={<InterviewPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
