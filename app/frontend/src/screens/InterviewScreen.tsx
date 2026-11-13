import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { api, ApiError } from '@/api';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/input';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import type { InterviewState, TurnView } from '@/types';
import { Loader2, Pause, Play, Send, Flag, WifiOff } from 'lucide-react';

const MAX_TURNS_SHOWN = 10;

export function InterviewScreen({ interviewId, onFinished, onLogout }: {
  interviewId: string;
  onFinished: () => void;
  onLogout: () => void;
}) {
  const [state, setState] = useState<InterviewState | null>(null);
  const [pending, setPending] = useState<TurnView | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(!navigator.onLine);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLOListElement>(null);

  async function refresh() {
    const s = await api<InterviewState>(`/interviews/${interviewId}`);
    setState(s);
    setPending(s.pending_turn);
    return s;
  }

  async function askNext(version: number) {
    const res = await api<{ turn: TurnView | null; version: number; done?: boolean }>(
      `/interviews/${interviewId}/next-question`,
      { method: 'POST', json: { version } },
    );
    if (res.done || !res.turn) {
      await api(`/interviews/${interviewId}/finish`, { method: 'POST', json: { version: res.version } });
      onFinished();
      return;
    }
    await refresh();
  }

  useEffect(() => {
    const up = () => setOffline(false);
    const down = () => setOffline(true);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    return () => {
      window.removeEventListener('online', up);
      window.removeEventListener('offline', down);
    };
  }, []);

  useEffect(() => {
    setBusy(true);
    refresh()
      .then(async (s) => {
        if (s.status === 'FINISHED') onFinished();
        else if (!s.pending_turn && s.status === 'ACTIVE') await askNext(s.version);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Не вдалося відкрити розмову.'))
      .finally(() => setBusy(false));
    // load once for this interview
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewId]);

  useEffect(() => {
    if (pending) inputRef.current?.focus();
  }, [pending?.id]);

  useEffect(() => {
    logRef.current?.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [state?.turns.length]);

  async function send(e?: FormEvent) {
    e?.preventDefault();
    if (!pending || !state || !draft.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/interviews/${interviewId}/answers`, {
        method: 'POST',
        json: {
          turn_id: pending.id,
          text: draft.trim(),
          version: state.version,
          idempotency_key: crypto.randomUUID(),
        },
      });
      setDraft('');
      const fresh = await refresh();
      if (fresh.status === 'ACTIVE') await askNext(fresh.version);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('Розмова оновилась в іншій вкладці. Ми завантажили актуальний стан.');
        await refresh();
      } else {
        setError(err instanceof ApiError ? err.message : 'Не вдалося надіслати відповідь. Ваш текст збережено.');
      }
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  }

  async function lifecycle(action: 'pause' | 'resume' | 'finish') {
    if (!state) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/interviews/${interviewId}/${action}`, { method: 'POST', json: { version: state.version } });
      if (action === 'finish') onFinished();
      else await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не вдалося змінити стан розмови.');
    } finally {
      setBusy(false);
    }
  }

  const answered = state?.turns.filter((t) => t.answer_text !== null).length ?? 0;
  const shown = state?.turns.slice(-MAX_TURNS_SHOWN) ?? [];

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Розмова про ваш досвід</h1>
        <div className="flex items-center gap-3">
          <Progress value={Math.min(100, answered * 10)} label="Прогрес розмови" className="w-32" />
          <Badge variant="info">Відповідей: {answered}</Badge>
          <Button variant="ghost" size="sm" onClick={onLogout}>Вийти</Button>
        </div>
      </header>
      {offline && (
        <Alert role="status" className="flex items-center gap-2">
          <WifiOff className="size-4" aria-hidden="true" />
          Немає мережі. Відповідь не буде надіслано, поки з’єднання не відновиться.
        </Alert>
      )}
      {error && <Alert role="alert">{error}</Alert>}
      <section aria-label="Листування" className="flex min-h-64 flex-col rounded-xl border border-slate-200 bg-white p-4">
        <ol ref={logRef} aria-live="polite" className="flex flex-col gap-3">
          {shown.map((t) => (
            <li key={t.id} className="flex flex-col gap-2">
              <p className="max-w-[85%] rounded-lg bg-slate-100 p-3 text-sm text-slate-900">
                <span className="sr-only">Питання: </span>
                {t.question_text}
              </p>
              {t.answer_text !== null && (
                <p className="ml-auto max-w-[85%] rounded-lg bg-blue-600 p-3 text-sm text-white">
                  <span className="sr-only">Ваша відповідь: </span>
                  {t.answer_text}
                </p>
              )}
              {!t.graded && <span className="text-xs text-slate-500">Питання без автоматичної оцінки</span>}
            </li>
          ))}
        </ol>
        {busy && !pending && (
          <p role="status" className="mt-3 flex items-center gap-2 text-sm text-slate-600">
            <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            Готуємо наступне питання…
          </p>
        )}
      </section>
      {pending && state?.status === 'ACTIVE' && (
        <form onSubmit={send} className="flex flex-col gap-2">
          <label htmlFor="answer" className="text-sm font-medium text-slate-700">Ваша відповідь</label>
          <Textarea
            id="answer"
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            maxLength={4000}
            placeholder="Опишіть конкретний приклад із вашого досвіду"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-slate-500">Enter — надіслати, Shift+Enter — новий рядок.</p>
            <div className="flex gap-2">
              <Button type="submit" disabled={busy || !draft.trim() || offline}>
                <Send className="size-4" aria-hidden="true" />
                Надіслати
              </Button>
            </div>
          </div>
        </form>
      )}
      <footer className="flex flex-wrap gap-2">
        {state?.status === 'ACTIVE' && (
          <Button variant="outline" onClick={() => void lifecycle('pause')} disabled={busy}>
            <Pause className="size-4" aria-hidden="true" />
            Призупинити
          </Button>
        )}
        {state?.status === 'PAUSED' && (
          <Button variant="outline" onClick={() => void lifecycle('resume')} disabled={busy}>
            <Play className="size-4" aria-hidden="true" />
            Продовжити
          </Button>
        )}
        <Button variant="ghost" onClick={() => void lifecycle('finish')} disabled={busy || !answered}>
          <Flag className="size-4" aria-hidden="true" />
          Завершити і переглянути результати
        </Button>
      </footer>
    </main>
  );
}
