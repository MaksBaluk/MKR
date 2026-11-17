import { useEffect, useId, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Archive, BarChart3, CheckCircle2, ChevronDown, History, Loader2, MapPin, Pencil, Plus, UsersRound } from 'lucide-react';
import { api, ApiError } from '@/api';
import { ErrorRetry } from '@/components/ErrorRetry';
import { ProfileFields } from '@/components/ProfileFields';
import { SelfRatingList } from '@/components/SelfRatingList';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog } from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useStartAttempt } from '@/hooks/useStartAttempt';
import { useActiveProfile } from '@/lib/activeProfile';
import {
  activeAfterArchive, attemptStatusLabel, formatDate, profileFormFrom, startLabel, trackLabel,
  validateProfileForm, type ProfileBody, type ProfileFormErrors,
} from '@/lib/profiles';
import { cn } from '@/lib/utils';
import { yearsCount } from '@/lib/vacancies';
import type { AttemptSummary, CandidateProfile, SelfRatingValue } from '@/types';

const errorText = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback);

export function ProfileFormDialog({ open, profile, onClose, onSubmit, submitLabel, hint }: {
  open: boolean;
  profile: CandidateProfile | null;
  onClose: () => void;
  onSubmit: (body: ProfileBody) => Promise<void>;
  submitLabel: string;
  hint?: string;
}) {
  const [form, setForm] = useState(() => profileFormFrom(profile));
  const [errors, setErrors] = useState<ProfileFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const base = useId();
  const id = (k: string) => `${base}-${k}`;

  useEffect(() => {
    if (!open) return;
    setForm(profileFormFrom(profile));
    setErrors({});
    setServerError(null);
  }, [open, profile]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const { errors: errs, body } = validateProfileForm(form);
    setErrors(errs);
    if (!body) {
      document.getElementById(id(Object.keys(errs)[0]))?.focus();
      return;
    }
    setBusy(true);
    setServerError(null);
    try {
      await onSubmit(body);
    } catch (err) {
      setServerError(errorText(err, 'Не вдалося зберегти профіль. Спробуйте ще раз.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={profile ? 'Редагувати профіль' : 'Новий профіль'}>
      <form noValidate onSubmit={submit} className="flex flex-col gap-4">
        {hint && <p className="text-sm text-ink-muted">{hint}</p>}
        <ProfileFields form={form} errors={errors} idBase={base}
          onChange={(k, v) => setForm((f) => ({ ...f, [k]: v }))} />
        {serverError && <Alert role="alert" variant="danger">{serverError}</Alert>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Скасувати</Button>
          <Button type="submit" disabled={busy}>
            {busy && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
            {submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function AttemptHistory({ attempts }: { attempts: AttemptSummary[] }) {
  if (attempts.length === 0) return <p className="text-sm text-ink-muted">Спроб ще немає.</p>;
  return (
    <ol className="flex flex-col divide-y divide-line rounded-xl border border-line">
      {attempts.map((a) => (
        <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm">
          <span className="font-medium text-ink">Спроба {a.attempt_no}</span>
          <Badge variant={a.status === 'FINISHED' ? 'success' : a.status === 'ACTIVE' ? 'info' : 'warning'}>
            {attemptStatusLabel(a.status)}
          </Badge>
          <span className="w-full text-xs text-ink-muted sm:w-auto">
            {formatDate(a.created_at)} · відповідей: {a.answers_count} · тем: {a.topics_used}
          </span>
        </li>
      ))}
    </ol>
  );
}

export function SelfRatings({ profile }: { profile: CandidateProfile }) {
  const [items, setItems] = useState<SelfRatingValue[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    api<{ items: SelfRatingValue[] }>(`/profiles/${encodeURIComponent(profile.id)}/self-ratings`)
      .then((r) => live && setItems(r.items))
      .catch((err) => live && setError(errorText(err, 'Не вдалося завантажити самооцінку.')));
    return () => {
      live = false;
    };
  }, [profile.id, nonce]);
  if (error) return <ErrorRetry message={error} onRetry={() => setNonce((n) => n + 1)} />;
  if (!items) return <Skeleton className="h-32" />;
  if (!profile.track) return <p className="text-sm text-ink-muted">Оберіть напрям, щоб оцінити свої дії.</p>;
  return (
    <SelfRatingList key={profile.track} track={profile.track} profileId={profile.id}
      initial={Object.fromEntries(items.map((r) => [r.action_id, r.value]))} />
  );
}

function Expander({ id, label, icon: Icon, open, onToggle }: {
  id: string; label: string; icon: typeof History; open: boolean; onToggle: () => void;
}) {
  return (
    <Button variant="ghost" size="sm" aria-expanded={open} aria-controls={id} onClick={onToggle} className="justify-start">
      <Icon className="size-4" aria-hidden="true" />{label}
      <ChevronDown className={cn('size-4 transition-transform motion-reduce:transition-none', open && 'rotate-180')} aria-hidden="true" />
    </Button>
  );
}

function ProfileCard({ profile, isActive, onEdit, onArchive, start }: {
  profile: CandidateProfile;
  isActive: boolean;
  onEdit: () => void;
  onArchive: () => void;
  start: ReturnType<typeof useStartAttempt>;
}) {
  const { setActive } = useActiveProfile();
  const navigate = useNavigate();
  const [attempts, setAttempts] = useState<AttemptSummary[] | null>(null);
  const [attemptsError, setAttemptsError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [panel, setPanel] = useState<'history' | 'self' | null>(null);
  const ids = { history: useId(), self: useId() };
  const pending = start.pendingId === profile.id;

  // Needed for the start button text and the last finished date; skipped for profiles without attempts.
  useEffect(() => {
    if (profile.attempts_count === 0) {
      setAttempts([]);
      return;
    }
    let live = true;
    setAttemptsError(null);
    api<{ items: AttemptSummary[] }>(`/profiles/${encodeURIComponent(profile.id)}/attempts`)
      .then((r) => live && setAttempts(r.items))
      .catch((err) => live && setAttemptsError(errorText(err, 'Не вдалося завантажити спроби.')));
    return () => {
      live = false;
    };
  }, [profile.id, profile.attempts_count, nonce]);

  const lastFinished = attempts?.find((a) => a.status === 'FINISHED') ?? null;
  const facts = [
    profile.desired_title && { k: 'Бажана посада', v: profile.desired_title },
    profile.years_experience !== null && { k: 'Досвід', v: yearsCount(profile.years_experience) },
    { k: 'Спроб', v: String(profile.attempts_count) },
    profile.latest_finished_attempt_id && { k: 'Остання завершена', v: lastFinished ? formatDate(lastFinished.created_at) : '…' },
  ].filter(Boolean) as { k: string; v: string }[];

  return (
    <Card className={cn('flex flex-col gap-4 p-4 sm:p-5', isActive && 'border-primary ring-1 ring-primary')}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-ink [overflow-wrap:anywhere]">{profile.name}</h2>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-ink-muted">
            <span>{trackLabel(profile.track)}</span>
            {profile.location && (
              <span className="inline-flex items-center gap-1"><span aria-hidden="true" className="text-line-strong">·</span>
                <MapPin className="size-3.5" aria-hidden="true" />{profile.location}</span>
            )}
          </p>
        </div>
        {isActive && <Badge variant="success"><CheckCircle2 className="size-3.5" aria-hidden="true" />Активний</Badge>}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {facts.map((f) => (
          <div key={f.k} className="min-w-0">
            <dt className="text-xs text-ink-subtle">{f.k}</dt>
            <dd className="truncate font-medium text-ink">{f.v}</dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void start.start(profile.id)} disabled={start.pendingId !== null || attempts === null}>
          {pending && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
          {startLabel(profile.attempts_count, attempts)}
        </Button>
        {profile.latest_finished_attempt_id && (
          <Button variant="outline" onClick={() => { setActive(profile.id); navigate('/results'); }}>
            <BarChart3 className="size-4" aria-hidden="true" />Переглянути результати
          </Button>
        )}
        {!isActive && <Button variant="outline" onClick={() => setActive(profile.id)}>Зробити активним</Button>}
      </div>
      {start.error?.profileId === profile.id && <Alert role="alert" variant="danger">{start.error.message}</Alert>}
      {attemptsError && <ErrorRetry message={attemptsError} onRetry={() => setNonce((n) => n + 1)} />}

      <div className="flex flex-wrap gap-1 border-t border-line pt-3">
        <Expander id={ids.history} label="Історія спроб" icon={History} open={panel === 'history'}
          onToggle={() => setPanel((p) => (p === 'history' ? null : 'history'))} />
        <Expander id={ids.self} label="Самооцінка" icon={UsersRound} open={panel === 'self'}
          onToggle={() => setPanel((p) => (p === 'self' ? null : 'self'))} />
        <span className="flex-1" />
        <Button variant="ghost" size="sm" onClick={onEdit} aria-label={`Редагувати профіль «${profile.name}»`}>
          <Pencil className="size-4" aria-hidden="true" />Редагувати
        </Button>
        <Button variant="ghost" size="sm" onClick={onArchive} aria-label={`Архівувати профіль «${profile.name}»`}
          className="text-danger-ink hover:bg-danger-soft hover:text-danger-ink">
          <Archive className="size-4" aria-hidden="true" />Архівувати
        </Button>
      </div>
      <div id={ids.history} hidden={panel !== 'history'}>
        {panel === 'history' && (attempts ? <AttemptHistory attempts={attempts} /> : <Skeleton className="h-20" />)}
      </div>
      <div id={ids.self} hidden={panel !== 'self'}>
        {panel === 'self' && <SelfRatings profile={profile} />}
      </div>
    </Card>
  );
}

export function ProfilesScreen() {
  const { profiles, active, status, error, reload, setActive } = useActiveProfile();
  const start = useStartAttempt();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<CandidateProfile | null>(null);
  const [archiving, setArchiving] = useState<CandidateProfile | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  /** Create the profile, make it active and open its page. The interview starts from there, by the candidate. */
  async function create(body: ProfileBody) {
    const p = await api<CandidateProfile>('/profiles', { method: 'POST', json: body });
    setCreating(false);
    setActive(p.id);
    await reload();
    navigate('/profile');
  }

  async function update(body: ProfileBody) {
    if (!editing) return;
    await api<CandidateProfile>(`/profiles/${encodeURIComponent(editing.id)}`, { method: 'PUT', json: body });
    setEditing(null);
    setNotice('Зміни збережено.');
    await reload();
  }

  async function archive() {
    if (!archiving || archiveBusy) return;
    setArchiveBusy(true);
    setArchiveError(null);
    try {
      await api(`/profiles/${encodeURIComponent(archiving.id)}`, { method: 'DELETE' });
      const next = activeAfterArchive(profiles, archiving.id, active?.id ?? null);
      if (next) setActive(next);
      setNotice(`Профіль «${archiving.name}» архівовано. Його спроби й результати збережено.`);
      setArchiving(null);
      await reload();
    } catch (err) {
      setArchiveError(errorText(err, 'Не вдалося архівувати профіль.'));
    } finally {
      setArchiveBusy(false);
    }
  }

  if (status === 'loading')
    return (
      <div className="grid gap-4 md:grid-cols-2" aria-busy="true">
        <p role="status" className="sr-only">Завантаження профілів…</p>
        <Skeleton className="h-64" /><Skeleton className="h-64" />
      </div>
    );
  if (status === 'error') return <ErrorRetry message={error} onRetry={() => void reload()} />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-prose text-sm text-ink-muted">
          Кожен профіль має власну співбесіду, результати й самооцінку. Активний профіль визначає, що показують «Результати» та «Профіль ринку».
        </p>
        <Button onClick={() => setCreating(true)} disabled={start.pendingId !== null}>
          <Plus className="size-4" aria-hidden="true" />Створити профіль
        </Button>
      </div>
      <div role="status" aria-live="polite" className={notice ? '' : 'sr-only'}>
        {notice && <Alert variant="success">{notice}</Alert>}
      </div>
      {start.pendingId && !profiles.some((p) => p.id === start.pendingId) && (
        <p role="status" className="text-sm text-ink-muted">Розпочинаємо співбесіду…</p>
      )}

      {profiles.length === 0 ? (
        <EmptyState icon={UsersRound} title="Профілів ще немає"
          action={<Button onClick={() => setCreating(true)}><Plus className="size-4" aria-hidden="true" />Створити профіль</Button>}>
          Створіть профіль: відкриється його сторінка, звідки можна почати співбесіду.
        </EmptyState>
      ) : (
        <ul className="grid items-start gap-4 md:grid-cols-2">
          {profiles.map((p) => (
            <li key={p.id}>
              <ProfileCard profile={p} isActive={p.id === active?.id} start={start}
                onEdit={() => { setNotice(null); setEditing(p); }}
                onArchive={() => { setNotice(null); setArchiveError(null); setArchiving(p); }} />
            </li>
          ))}
        </ul>
      )}

      <ProfileFormDialog open={creating} profile={null} onClose={() => setCreating(false)} onSubmit={create}
        submitLabel="Створити й почати співбесіду" hint="Після створення одразу почнеться перша співбесіда для цього профілю." />
      <ProfileFormDialog open={editing !== null} profile={editing} onClose={() => setEditing(null)} onSubmit={update}
        submitLabel="Зберегти" hint="Зміни не впливають на вже завершені спроби: їхні дані зафіксовано." />
      <Dialog open={archiving !== null} onClose={() => setArchiving(null)} title="Архівувати профіль?">
        <div className="flex flex-col gap-4">
          <p className="text-sm text-ink-muted">
            Профіль «{archiving?.name}» зникне зі списку. Спроби, оцінки й результати залишаться збереженими на сервері.
          </p>
          {archiveError && <Alert role="alert" variant="danger">{archiveError}</Alert>}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={() => setArchiving(null)}>Скасувати</Button>
            <Button onClick={() => void archive()} disabled={archiveBusy} className="bg-danger text-white hover:bg-danger/90">
              {archiveBusy && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
              Архівувати
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
