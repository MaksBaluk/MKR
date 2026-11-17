import { useEffect, useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, MessageSquare, UsersRound } from 'lucide-react';
import { api, ApiError } from '@/api';
import { CompetencyRatings } from '@/components/CompetencyRatings';
import { ErrorRetry } from '@/components/ErrorRetry';
import { ProfileFields } from '@/components/ProfileFields';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useStartAttempt } from '@/hooks/useStartAttempt';
import { useActiveProfile } from '@/lib/activeProfile';
import {
  isProfileComplete, profileFormFrom, validateProfileForm, type ProfileForm, type ProfileFormErrors,
} from '@/lib/profiles';
import { AttemptHistory } from '@/screens/ProfilesScreen';
import type { AttemptSummary, CandidateProfile, ProfileResults } from '@/types';

/** Everything about one candidate profile on one page: data, competencies, history, start. */
export function ProfileHub({ profile }: { profile: CandidateProfile }) {
  const { reload } = useActiveProfile();
  const start = useStartAttempt();
  const [form, setForm] = useState<ProfileForm>(() => profileFormFrom(profile));
  const [errors, setErrors] = useState<ProfileFormErrors>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<AttemptSummary[] | null>(null);
  const [results, setResults] = useState<ProfileResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const pid = encodeURIComponent(profile.id);
  const idBase = useId();
  // Reload the attempt-dependent blocks when the profile's attempt state changes (new attempt, finished attempt).
  const attemptKey = `${profile.open_attempt?.id ?? ''}|${profile.latest_finished_attempt?.id ?? ''}`;

  useEffect(() => {
    let live = true;
    setError(null);
    Promise.all([
      api<{ items: AttemptSummary[] }>(`/profiles/${pid}/attempts`),
      api<ProfileResults>(`/profiles/${pid}/results?page_size=1`),
    ])
      .then(([a, r]) => {
        if (!live) return;
        setAttempts(a.items);
        setResults(r);
      })
      .catch((err) => live && setError(err instanceof ApiError ? err.message : 'Не вдалося завантажити дані профілю.'));
    return () => {
      live = false;
    };
  }, [pid, attemptKey, nonce]);

  const saved = profileFormFrom(profile);
  const dirty = (Object.keys(saved) as (keyof ProfileForm)[]).some((k) => saved[k] !== form[k]);

  async function save(next: ProfileForm = form) {
    const { errors: errs, body } = validateProfileForm(next);
    setErrors(errs);
    if (!body) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api<CandidateProfile>(`/profiles/${pid}`, { method: 'PUT', json: body });
      setNotice('Зміни збережено.');
      await reload();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Не вдалося зберегти профіль. Спробуйте ще раз.');
    } finally {
      setSaving(false);
    }
  }

  function change(key: keyof ProfileForm, value: string) {
    const next = { ...form, [key]: value };
    setForm(next);
    setNotice(null);
    // Choosing the direction is saved at once: the competencies for it appear right below.
    if (key === 'track' && value !== '') void save(next);
  }

  const open = profile.open_attempt;
  const complete = isProfileComplete(profile);
  const busy = start.pendingId === profile.id;
  const competencies = results?.competencies ?? [];
  const status = open ? 'Співбесіда не завершена'
    : profile.attempts_count > 0 ? `Співбесід пройдено: ${profile.attempts_count}` : 'Співбесіду ще не пройдено';

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-tight text-ink [overflow-wrap:anywhere]">Профіль «{profile.name}»</h2>
          <p className="mt-1 text-sm text-ink-muted">{status}</p>
          {!open && (!complete || dirty) && (
            <p className="mt-1 text-sm text-warning-ink">
              {dirty ? 'Збережіть зміни, щоб почати співбесіду.' : 'Щоб почати співбесіду, оберіть напрям, рівень і вкажіть роки досвіду.'}
            </p>
          )}
        </div>
        {open ? (
          <Button asChild size="lg"><Link to={`/interview/${open.id}`}><MessageSquare className="size-4" aria-hidden="true" />Продовжити співбесіду</Link></Button>
        ) : (
          <Button size="lg" onClick={() => void start.start(profile.id)} disabled={start.pendingId !== null || !complete || dirty}>
            {busy ? <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              : <MessageSquare className="size-4" aria-hidden="true" />}
            {profile.attempts_count > 0 ? 'Пройти ще раз' : 'Розпочати співбесіду'}
          </Button>
        )}
      </Card>
      {start.error && start.error.profileId === profile.id && <Alert role="alert" variant="danger">{start.error.message}</Alert>}

      <Card>
        <CardHeader>
          <CardTitle>Про вас</CardTitle>
          <CardDescription>Рівень і роки досвіду враховуються в питаннях співбесіди.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ProfileFields form={form} errors={errors} idBase={idBase} onChange={change} />
          {saveError && <Alert role="alert" variant="danger">{saveError}</Alert>}
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => void save()} disabled={saving || !dirty}>
              {saving && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
              Зберегти зміни
            </Button>
            <span role="status" aria-live="polite" className="text-sm text-ink-muted">{notice}</span>
          </div>
        </CardContent>
      </Card>

      {profile.track && (
        <Card>
          <CardHeader>
            <CardTitle>Компетентності</CardTitle>
            <CardDescription>
              Самооцінка необов’язкова. Після співбесіди поруч з’явиться оцінка LLM: це оцінка наданих відповідей,
              а не перевірений досвід, змінити її не можна.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CompetencyRatings key={profile.track} track={profile.track} profileId={profile.id} competencies={competencies} />
          </CardContent>
        </Card>
      )}

      {error ? <ErrorRetry message={error} onRetry={() => setNonce((n) => n + 1)} /> : !attempts ? (
        <Skeleton className="h-24" />
      ) : (
        <Card>
          <CardHeader><CardTitle>Історія спроб</CardTitle></CardHeader>
          <CardContent><AttemptHistory attempts={attempts} /></CardContent>
        </Card>
      )}
    </div>
  );
}

/** Route wrapper: the page follows the active profile and has a helpful empty state without one. */
export function ProfileHubPage() {
  const { status, active, error, reload } = useActiveProfile();
  if (status === 'loading') return <Skeleton className="h-64" />;
  if (status === 'error') return <ErrorRetry message={error} onRetry={() => void reload()} />;
  if (!active)
    return (
      <EmptyState icon={UsersRound} title="Профілів ще немає"
        action={<Button asChild><Link to="/profiles">Створити профіль</Link></Button>}>
        Створіть профіль, щоб оцінити свої компетентності.
      </EmptyState>
    );
  return <ProfileHub key={active.id} profile={active} />;
}
