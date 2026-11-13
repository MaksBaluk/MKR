import { useId, useState, type FormEvent } from 'react';
import { api, ApiError } from '@/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert } from '@/components/ui/alert';
import { SelfRatingList } from '@/components/SelfRatingList';
import type { CohortResponse, Profile } from '@/types';
import { LogOut, MessageSquare } from 'lucide-react';

const TRACKS = [
  { value: 'python', label: 'Python-розробка' },
  { value: 'marketing', label: 'Маркетинг' },
  { value: 'design', label: 'Дизайн' },
];

export function ProfileScreen({ profile, onSaved, onStarted, onLogout }: {
  profile: Profile;
  onSaved: (p: Profile) => void;
  onStarted: (interviewId: string, cohortId: string) => void;
  onLogout: () => void;
}) {
  const [name, setName] = useState(profile.display_name);
  const [track, setTrack] = useState(profile.track);
  const [title, setTitle] = useState(profile.desired_title);
  const [years, setYears] = useState(profile.years_experience?.toString() ?? '');
  const [location, setLocation] = useState(profile.location);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ids = { name: useId(), track: useId(), title: useId(), years: useId(), location: useId() };
  const initialRatings = Object.fromEntries(profile.self_ratings.map((r) => [r.action_id, r.value]));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = await api<Profile>('/profile', {
        method: 'PUT',
        json: {
          display_name: name,
          track,
          desired_title: title,
          years_experience: years === '' ? null : Number(years),
          location,
        },
      });
      onSaved(saved);
      const cohort = await api<CohortResponse>('/cohorts/auto', { method: 'POST' });
      if (cohort.empty || !cohort.cohort_id) {
        setError('Для цього треку ще немає вакансій у каталозі. Спробуйте інший трек.');
        return;
      }
      const iv = await api<{ id: string }>('/interviews', { method: 'POST', json: { cohort_id: cohort.cohort_id } });
      onStarted(iv.id, cohort.cohort_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не вдалося зберегти профіль. Перевірте дані та спробуйте ще раз.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Ваш профіль</h1>
        <Button variant="ghost" onClick={onLogout}>
          <LogOut className="size-4" aria-hidden="true" />
          Вийти
        </Button>
      </header>
      <Card>
        <CardHeader>
          <CardTitle>Основні дані</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit} noValidate>
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.name}>Ім’я</Label>
              <Input id={ids.name} value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.track}>Професійний трек</Label>
              <select id={ids.track} value={track} onChange={(e) => setTrack(e.target.value)}
                className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm">
                {TRACKS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.title}>Бажана посада</Label>
              <Input id={ids.title} value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.years}>Років досвіду</Label>
              <Input id={ids.years} type="number" min={0} max={70} value={years} onChange={(e) => setYears(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Label htmlFor={ids.location}>Місто або формат роботи</Label>
              <Input id={ids.location} value={location} onChange={(e) => setLocation(e.target.value)} />
            </div>
            {error && <Alert role="alert" className="sm:col-span-2">{error}</Alert>}
            <div className="sm:col-span-2">
              <Button type="submit" disabled={busy}>
                <MessageSquare className="size-4" aria-hidden="true" />
                {busy ? 'Готуємо розмову…' : 'Зберегти та почати розмову'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Самооцінка дій</CardTitle>
        </CardHeader>
        <CardContent>
          <SelfRatingList track={track} initial={initialRatings} />
        </CardContent>
      </Card>
    </main>
  );
}
