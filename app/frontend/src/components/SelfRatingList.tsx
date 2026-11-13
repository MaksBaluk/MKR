import { useEffect, useState } from 'react';
import { api, ApiError } from '@/api';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';

interface Competency {
  id: string;
  label_uk: string;
}

export function SelfRatingList({ track, initial, onSaved }: {
  track: string;
  initial: Record<string, number | null>;
  onSaved?: () => void;
}) {
  const [actions, setActions] = useState<Competency[]>([]);
  const [values, setValues] = useState<Record<string, number | null>>(initial);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  useEffect(() => {
    api<Competency[]>(`/competencies?track=${encodeURIComponent(track)}`)
      .then(setActions)
      .catch(() => setError('Не вдалося завантажити список професійних дій.'));
  }, [track]);

  async function save(actionId: string, value: number | null) {
    setSavingId(actionId);
    setError(null);
    try {
      await api(`/profile/self-ratings/${actionId}`, { method: 'PUT', json: { value } });
      setValues((prev) => ({ ...prev, [actionId]: value }));
      onSaved?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не вдалося зберегти оцінку.');
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-600">
        Оцініть, наскільки впевнено ви виконуєте кожну дію. Це ваша самооцінка: вона редагується, але не замінює оцінку розмови.
      </p>
      {error && <Alert role="alert">{error}</Alert>}
      <ul className="flex flex-col gap-3">
        {actions.map((a) => {
          const value = values[a.id] ?? null;
          const id = `sr-${a.id}`;
          return (
            <li key={a.id} className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-3">
              <label htmlFor={id} className="text-sm font-medium text-slate-800">
                {a.label_uk}
              </label>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  id={id}
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  disabled={value === null}
                  value={value === null ? 0 : Math.round(value * 100)}
                  onChange={(e) => setValues((prev) => ({ ...prev, [a.id]: Number(e.target.value) / 100 }))}
                  className="min-w-40 flex-1 accent-blue-600"
                  aria-valuetext={value === null ? 'не вказано' : `${Math.round(value * 100)} з 100`}
                />
                <span className="w-24 text-sm text-slate-600">
                  {value === null ? 'Не вказано' : `${Math.round(value * 100)} з 100`}
                </span>
                <Button size="sm" variant="outline" disabled={savingId === a.id}
                  onClick={() => void save(a.id, values[a.id] ?? null)}>
                  {savingId === a.id ? 'Зберігаємо…' : 'Зберегти'}
                </Button>
                <Button size="sm" variant="ghost"
                  onClick={() => void save(a.id, value === null ? 0 : null)}>
                  {value === null ? 'Вказати оцінку' : 'Не знаю'}
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
