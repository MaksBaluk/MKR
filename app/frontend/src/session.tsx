import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, ApiError, getToken, onUnauthorized, setToken } from '@/api';
import type { SessionInterview } from '@/lib/navigation';
import type { Profile } from '@/types';

type Status = 'loading' | 'anonymous' | 'ready' | 'error';
type InterviewRef = { interview: { id: string; cohort_id: string } | null };

interface SessionValue {
  status: Status;
  error: string | null;
  profile: Profile | null;
  llmConfigured: boolean;
  /** Open interview if any, otherwise the latest finished one (same priority as the pre-router app). */
  interview: SessionInterview | null;
  /** Set once after a successful boot so the shell can resume the candidate's stage. */
  justBooted: boolean;
  /** True after the server rejected the stored token mid-session (login page shows a notice). */
  sessionExpired: boolean;
  consumeBoot: () => void;
  boot: () => Promise<void>;
  refreshInterview: () => Promise<SessionInterview | null>;
  reloadProfile: () => Promise<void>;
  setProfile: (p: Profile) => void;
  signOut: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

async function fetchInterview(): Promise<SessionInterview | null> {
  const open = await api<InterviewRef>('/interviews/active');
  if (open.interview) return { ...open.interview, status: 'active' };
  const done = await api<InterviewRef>('/interviews/latest-finished');
  return done.interview ? { ...done.interview, status: 'finished' } : null;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>(getToken() ? 'loading' : 'anonymous');
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [llmConfigured, setLlmConfigured] = useState(false);
  const [interview, setInterview] = useState<SessionInterview | null>(null);
  const [justBooted, setJustBooted] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);

  const clear = useCallback(() => {
    setToken(null);
    setProfile(null);
    setInterview(null);
    setJustBooted(false);
    setStatus('anonymous');
  }, []);

  const signOut = useCallback(() => {
    setSessionExpired(false);
    clear();
  }, [clear]);

  /** Any authenticated 401: drop the session; the route guard redirects to /login with `from`. */
  const expire = useCallback(() => {
    setSessionExpired(true);
    clear();
  }, [clear]);

  useEffect(() => onUnauthorized(expire), [expire]);

  const boot = useCallback(async () => {
    setError(null);
    if (!getToken()) {
      setStatus('anonymous');
      return;
    }
    setStatus('loading');
    try {
      const p = await api<Profile>('/profile');
      const cfg = await api<{ llm: { configured: boolean } }>('/config');
      const iv = await fetchInterview();
      setProfile(p);
      setLlmConfigured(cfg.llm.configured);
      setInterview(iv);
      setJustBooted(true);
      setSessionExpired(false);
      setStatus('ready');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) expire();
      else {
        setError(err instanceof Error ? err.message : 'Не вдалося завантажити дані.');
        setStatus('error');
      }
    }
  }, [expire]);

  const refreshInterview = useCallback(async () => {
    const iv = await fetchInterview();
    setInterview(iv);
    return iv;
  }, []);

  const reloadProfile = useCallback(async () => {
    setProfile(await api<Profile>('/profile'));
  }, []);

  useEffect(() => {
    void boot();
  }, [boot]);

  const value = useMemo<SessionValue>(
    () => ({
      status, error, profile, llmConfigured, interview, justBooted, sessionExpired,
      consumeBoot: () => setJustBooted(false),
      boot, refreshInterview, reloadProfile, setProfile, signOut,
    }),
    [status, error, profile, llmConfigured, interview, justBooted, sessionExpired, boot, refreshInterview, reloadProfile, signOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used inside SessionProvider');
  return ctx;
}
