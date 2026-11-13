import { useEffect, useState } from 'react';
import { api, getToken, setToken, ApiError } from '@/api';
import type { Profile } from '@/types';
import { AuthScreen } from '@/screens/AuthScreen';
import { WelcomeScreen } from '@/screens/WelcomeScreen';
import { ProfileScreen } from '@/screens/ProfileScreen';
import { InterviewScreen } from '@/screens/InterviewScreen';
import { ResultsScreen } from '@/screens/ResultsScreen';
import { Loader2 } from 'lucide-react';

type Stage = 'loading' | 'auth' | 'welcome' | 'profile' | 'interview' | 'results';

export default function App() {
  const [stage, setStage] = useState<Stage>('loading');
  const [profile, setProfile] = useState<Profile | null>(null);
  const [interviewId, setInterviewId] = useState<string | null>(null);
  const [cohortId, setCohortId] = useState<string | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [llmConfigured, setLlmConfigured] = useState(false);

  async function loadProfile() {
    const p = await api<Profile>('/profile');
    setProfile(p);
    return p;
  }

  async function boot() {
    setBootError(null);
    if (!getToken()) {
      setStage('auth');
      return;
    }
    try {
      await loadProfile();
      const cfg = await api<{ llm: { configured: boolean } }>('/config');
      setLlmConfigured(cfg.llm.configured);
      const open = await api<{ interview: { id: string; cohort_id: string } | null }>('/interviews/active');
      if (open.interview) {
        setInterviewId(open.interview.id);
        setCohortId(open.interview.cohort_id);
        setStage('interview');
        return;
      }
      const done = await api<{ interview: { id: string; cohort_id: string } | null }>('/interviews/latest-finished');
      if (done.interview) {
        setInterviewId(done.interview.id);
        setCohortId(done.interview.cohort_id);
        setStage('results');
        return;
      }
      setStage('welcome');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setToken(null);
        setStage('auth');
      } else {
        setBootError(err instanceof Error ? err.message : 'Не вдалося завантажити дані.');
      }
    }
  }

  useEffect(() => {
    void boot();
    // boot runs once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function signedIn() {
    void boot();
  }

  function startInterview(id: string, cohort: string) {
    setInterviewId(id);
    setCohortId(cohort);
    setStage('interview');
  }

  function logout() {
    setToken(null);
    setProfile(null);
    setInterviewId(null);
    setCohortId(null);
    setStage('auth');
  }

  if (bootError) {
    return (
      <main className="mx-auto max-w-md p-4">
        <p role="alert" className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          {bootError}
        </p>
        <button className="mt-3 underline" onClick={() => void boot()}>
          Спробувати ще раз
        </button>
      </main>
    );
  }

  if (stage === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center gap-2 text-slate-600" role="status">
        <Loader2 className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        Завантаження…
      </div>
    );
  }

  if (stage === 'auth') return <AuthScreen onSignedIn={signedIn} />;
  if (stage === 'welcome') return <WelcomeScreen onContinue={() => setStage('profile')} onLogout={logout} />;
  if (stage === 'profile' && profile)
    return (
      <ProfileScreen
        profile={profile}
        onSaved={(p) => setProfile(p)}
        onStarted={startInterview}
        onLogout={logout}
      />
    );
  if (stage === 'interview' && interviewId && cohortId && profile)
    return (
      <InterviewScreen
        interviewId={interviewId}
        profile={profile}
        llmConfigured={llmConfigured}
        onFinished={() => setStage('results')}
        onLogout={logout}
      />
    );
  if (stage === 'results' && cohortId)
    return <ResultsScreen cohortId={cohortId} name={profile?.display_name ?? ''} onLogout={logout} onProfileChanged={() => void loadProfile()} />;
  return <AuthScreen onSignedIn={signedIn} />;
}
