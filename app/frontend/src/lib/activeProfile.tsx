import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, ApiError } from '@/api';
import { pickActiveId } from '@/lib/activeProfileSelect';
import type { CandidateProfile } from '@/types';

const KEY = 'cm_active_profile';

function readStored(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function writeStored(id: string): void {
  try {
    localStorage.setItem(KEY, id);
  } catch {
    /* storage unavailable: selection lives in memory only */
  }
}

interface ActiveProfileValue {
  profiles: CandidateProfile[];
  active: CandidateProfile | null;
  status: 'loading' | 'ready' | 'error';
  error: string | null;
  setActive: (id: string) => void;
  reload: () => Promise<void>;
}

const Ctx = createContext<ActiveProfileValue | null>(null);

/** Loads the candidate's profiles and remembers which one is active (Task 11 adds the switcher UI). */
export function ActiveProfileProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<CandidateProfile[]>([]);
  const [activeId, setActiveId] = useState<string | null>(readStored);
  const [status, setStatus] = useState<ActiveProfileValue['status']>('loading');
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const { items } = await api<{ items: CandidateProfile[] }>('/profiles');
      setProfiles(items);
      setActiveId((cur) => pickActiveId(items, cur ?? readStored()));
      setStatus('ready');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не вдалося завантажити профілі.');
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const setActive = useCallback((id: string) => {
    setActiveId(id);
    writeStored(id);
  }, []);

  const value = useMemo<ActiveProfileValue>(() => ({
    profiles, status, error, setActive, reload,
    active: profiles.find((p) => p.id === activeId) ?? null,
  }), [profiles, status, error, setActive, reload, activeId]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useActiveProfile(): ActiveProfileValue {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useActiveProfile must be used inside ActiveProfileProvider');
  return ctx;
}
