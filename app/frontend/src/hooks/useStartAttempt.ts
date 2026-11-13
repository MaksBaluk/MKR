import { useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '@/api';
import { useActiveProfile } from '@/lib/activeProfile';
import { useSession } from '@/session';

/**
 * Starts (or resumes: the API returns the open attempt) an interview for a profile, makes the profile active
 * and opens the interview. A ref guards against double clicks creating two requests.
 */
export function useStartAttempt() {
  const navigate = useNavigate();
  const { refreshInterview } = useSession();
  const { setActive, reload } = useActiveProfile();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<{ profileId: string; message: string } | null>(null);
  const inFlight = useRef(false);

  const start = useCallback(async (profileId: string) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setPendingId(profileId);
    setError(null);
    try {
      const a = await api<{ id: string }>(`/profiles/${encodeURIComponent(profileId)}/attempts`, { method: 'POST' });
      setActive(profileId);
      await Promise.all([refreshInterview().catch(() => null), reload()]);
      navigate(`/interview/${encodeURIComponent(a.id)}`);
    } catch (err) {
      setError({ profileId, message: err instanceof ApiError ? err.message : 'Не вдалося розпочати співбесіду. Спробуйте ще раз.' });
    } finally {
      inFlight.current = false;
      setPendingId(null);
    }
  }, [navigate, refreshInterview, setActive, reload]);

  return { start, pendingId, error };
}
