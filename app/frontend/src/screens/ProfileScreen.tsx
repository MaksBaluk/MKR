import { useId, useState, type FormEvent } from 'react';
import { api, ApiError } from '@/api';
import { SelfRatingList } from '@/components/SelfRatingList';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import type { CohortResponse, Profile } from '@/types';
import { Loader2, MessageSquare } from 'lucide-react';

const TRACKS = [
  { value: 'python', label: 'Python-розробка' },
  { value: 'marketing', label: 'Маркетинг' },
  { value: 'design', label: 'Дизайн' },
];

export function ProfileScreen({ profile, onSaved, onStarted }: {
  profile: Profile;
  onSaved: (p: Profile) => void;
  onStarted: (interviewId: string, cohortId: string) => void;
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
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-start">
      <Card>
        <CardHeader>
          <CardTitle>Основні дані</CardTitle>
          <CardDescription>За треком система добере вакансії для розмови. Обрати їх вручну до співбесіди не можна.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit} noValidate>
            <Field id={ids.name} label="Ім’я">
              <Input id={ids.name} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required minLength={2} />
            </Field>
            <Field id={ids.track} label="Професійний трек">
              <Select id={ids.track} value={track} onChange={(e) => setTrack(e.target.value)}>
                {TRACKS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </Select>
            </Field>
            <Field id={ids.title} label="Бажана посада">
              <Input id={ids.title} value={title} onChange={(e) => setTitle(e.target.value)} autoComplete="organization-title" />
            </Field>
            <Field id={ids.years} label="Років досвіду">
              <Input id={ids.years} type="number" inputMode="numeric" min={0} max={70} value={years} onChange={(e) => setYears(e.target.value)} />
            </Field>
            <Field id={ids.location} label="Місто або формат роботи" className="sm:col-span-2">
              <Input id={ids.location} value={location} onChange={(e) => setLocation(e.target.value)} />
            </Field>
            {error && <Alert role="alert" variant="danger" className="sm:col-span-2">{error}</Alert>}
            <div className="sm:col-span-2">
              <Button type="submit" size="lg" disabled={busy} className="w-full sm:w-auto">
                {busy ? <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  : <MessageSquare className="size-4" aria-hidden="true" />}
                {busy ? 'Готуємо розмову…' : 'Зберегти та почати розмову'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Самооцінка дій</CardTitle>
          <CardDescription>Необов’язково. Можна змінити пізніше в результатах.</CardDescription>
        </CardHeader>
        <CardContent>
          <SelfRatingList track={track} initial={initialRatings} />
        </CardContent>
      </Card>
    </div>
  );
}
