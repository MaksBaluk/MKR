import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '@/api';
import { Alert } from '@/components/ui/alert';
import { CheckCircle2, Loader2 } from 'lucide-react';

interface Competency {
  id: string;
  label_uk: string;
}

type SaveState = 'idle' | 'saving' | 'saved';

export function SelfRatingList({ track, initial, onSaved, profileId }: {
  track: string;
  initial: Record<string, number | null>;
  onSaved?: () => void;
  /** Save to this candidate profile; without it the legacy account-level endpoint (default profile) is used. */
  profileId?: string;
}) {
  const [actions, setActions] = useState<Competency[]>([]);
  const [values, setValues] = useState<Record<string, number | null>>(initial);
  const [state, setState] = useState<Record<string, SaveState>>({});
  const [error, setError] = useState<string | null>(null);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    api<Competency[]>(`/competencies?track=${encodeURIComponent(track)}`)
      .then(setActions)
      .catch(() => setError('Не вдалося завантажити список професійних дій.'));
  }, [track]);

  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);

  async function persist(actionId: string, value: number | null) {
    setState((s) => ({ ...s, [actionId]: 'saving' }));
    setError(null);
    try {
      const base = profileId ? `/profiles/${encodeURIComponent(profileId)}/self-ratings` : '/profile/self-ratings';
      await api(`${base}/${actionId}`, { method: 'PUT', json: { value } });
      setState((s) => ({ ...s, [actionId]: 'saved' }));
      onSaved?.();
    } catch (err) {
      setState((s) => ({ ...s, [actionId]: 'idle' }));
      setError(err instanceof ApiError ? err.message : 'Не вдалося зберегти оцінку.');
    }
  }

  function change(actionId: string, value: number | null) {
    setValues((v) => ({ ...v, [actionId]: value }));
    clearTimeout(timers.current[actionId]);
    timers.current[actionId] = setTimeout(() => void persist(actionId, value), 400);
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-muted">
        Оцініть, наскільки впевнено ви виконуєте кожну дію. Це ваша самооцінка: вона зберігається автоматично, але не замінює
        оцінку розмови.
      </p>
      {error && <Alert role="alert">{error}</Alert>}
      <ul className="grid gap-3 sm:grid-cols-2">
        {actions.map((a) => {
          const value = values[a.id] ?? null;
          const id = `sr-${a.id}`;
          const st = state[a.id] ?? 'idle';
          return (
            <li key={a.id} className="flex flex-col gap-2 rounded-xl border border-line bg-canvas p-3">
              <div className="flex items-center justify-between gap-2">
                <label htmlFor={id} className="text-sm font-semibold text-ink">{a.label_uk}</label>
                <span className="flex items-center gap-1 text-xs text-ink-subtle" aria-live="polite">
                  {st === 'saving' && <Loader2 className="size-3 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
                  {st === 'saved' && <CheckCircle2 className="size-3 text-success-ink" aria-hidden="true" />}
                  {st === 'saving' ? 'Зберігаємо…' : st === 'saved' ? 'Збережено' : ''}
                </span>
              </div>
              <input
                id={id}
                type="range"
                min={0}
                max={100}
                step={5}
                value={value === null ? 0 : Math.round(value * 100)}
                onChange={(e) => change(a.id, Number(e.target.value) / 100)}
                className={`w-full accent-primary ${value === null ? 'opacity-50' : ''}`}
                aria-valuetext={value === null ? 'не вказано' : `${Math.round(value * 100)} зі 100`}
              />
              <div className="flex items-center justify-between text-xs text-ink-muted">
                <span>{value === null ? 'Не вказано' : `${Math.round(value * 100)} зі 100`}</span>
                {value !== null && (
                  <button type="button" className="underline underline-offset-2 hover:text-ink"
                    onClick={() => change(a.id, null)}>
                    Не знаю
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
