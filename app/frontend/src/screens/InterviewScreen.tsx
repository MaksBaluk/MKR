import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { api, ApiError } from '@/api';
import { AppShell } from '@/components/AppShell';
import { ScoreBar } from '@/components/ScoreBar';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { timeLabel } from '@/lib/bands';
import type { AssessmentItem, InterviewState, Profile, TurnView } from '@/types';
import { Bot, Flag, Laptop, Lightbulb, Loader2, Pause, Play, Send, Target, User as UserIcon, WifiOff } from 'lucide-react';

const MAX_TOPICS = 10;
const TRACK_NAMES: Record<string, string> = { python: 'Python-розробник', marketing: 'Маркетолог', design: 'Дизайнер' };

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Reveals a bot message progressively, like a chatbot typing. Static for reduced motion or history. */
function BotText({ text, animate }: { text: string; animate: boolean }) {
  const [shown, setShown] = useState(animate && !prefersReducedMotion() ? 0 : text.length);
  useEffect(() => {
    if (shown >= text.length) return;
    const t = setTimeout(() => setShown((n) => Math.min(text.length, n + 2)), 14);
    return () => clearTimeout(t);
  }, [shown, text]);
  return (
    <>
      <span aria-hidden={shown < text.length}>{text.slice(0, shown)}</span>
      {shown < text.length && <span className="sr-only">{text}</span>}
    </>
  );
}

function TypingIndicator() {
  return (
    <div className="msg-in flex items-end gap-2" role="status" aria-label="Асистент друкує">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600">
        <Bot className="size-5" aria-hidden="true" />
      </span>
      <div className="flex gap-1 rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-3">
        {[0, 1, 2].map((i) => (
          <span key={i} className="typing-dot size-2 rounded-full bg-slate-400 motion-reduce:animate-none"
            style={{ animationDelay: `${i * 0.16}s` }} />
        ))}
      </div>
    </div>
  );
}

export function InterviewScreen({ interviewId, profile, llmConfigured, onFinished, onLogout }: {
  interviewId: string;
  profile: Profile;
  llmConfigured: boolean;
  onFinished: () => void;
  onLogout: () => void;
}) {
  const [state, setState] = useState<InterviewState | null>(null);
  const [pending, setPending] = useState<TurnView | null>(null);
  const [assessments, setAssessments] = useState<AssessmentItem[]>([]);
  const [draft, setDraft] = useState('');
  const [optimistic, setOptimistic] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(!navigator.onLine);
  const animateIds = useRef<Set<string>>(new Set());
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  async function refresh() {
    const s = await api<InterviewState>(`/interviews/${interviewId}`);
    setState(s);
    setPending(s.pending_turn);
    const a = await api<{ items: AssessmentItem[] }>(`/assessments?interview_id=${interviewId}`);
    setAssessments(a.items);
    return s;
  }

  async function askNext(version: number) {
    setThinking(true);
    try {
      const res = await api<{ turn: TurnView | null; version: number; done?: boolean }>(
        `/interviews/${interviewId}/next-question`,
        { method: 'POST', json: { version } },
      );
      if (res.done || !res.turn) {
        await api(`/interviews/${interviewId}/finish`, { method: 'POST', json: { version: res.version } });
        onFinished();
        return;
      }
      animateIds.current.add(res.turn.id);
      await refresh();
    } finally {
      setThinking(false);
    }
  }

  useEffect(() => {
    const up = () => setOffline(false);
    const down = () => setOffline(!navigator.onLine);
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
    // load once per interview
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewId]);

  useEffect(() => {
    if (pending && !thinking) inputRef.current?.focus();
  }, [pending?.id, thinking]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  }, [state?.turns.length, thinking, optimistic]);

  async function send(e?: FormEvent) {
    e?.preventDefault();
    const text = draft.trim();
    if (!pending || !state || !text || busy) return;
    setBusy(true);
    setError(null);
    setOptimistic(text);
    setDraft('');
    try {
      await api(`/interviews/${interviewId}/answers`, {
        method: 'POST',
        json: { turn_id: pending.id, text, version: state.version, idempotency_key: crypto.randomUUID() },
      });
      setOffline(false);
      setPending(null);
      const fresh = await refresh();
      setOptimistic(null);
      if (fresh.status === 'ACTIVE') await askNext(fresh.version);
    } catch (err) {
      setOptimistic(null);
      setDraft(text);
      if (err instanceof ApiError && err.status === 409) {
        setError('Розмова оновилась в іншій вкладці. Ми завантажили актуальний стан.');
        await refresh();
      } else {
        setError(err instanceof ApiError ? err.message : 'Не вдалося надіслати відповідь. Ваш текст збережено в полі.');
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

  const topics = state?.topics_used ?? 0;
  const turns = state?.turns ?? [];
  const latest = new Map<string, AssessmentItem>();
  assessments.forEach((a) => {
    if (a.score !== null) latest.set(a.action_id, a);
  });
  const profileItems = [...latest.values()].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 5);

  return (
    <AppShell
      title="Оцінювання компетентностей"
      name={profile.display_name}
      onLogout={onLogout}
      right={
        <div className="hidden items-center gap-3 sm:flex">
          <Progress value={(topics / MAX_TOPICS) * 100} label="Прогрес розмови" className="w-44" />
          <span className="text-sm font-medium text-slate-600">{topics}/{MAX_TOPICS} тем</span>
        </div>
      }
    >
      {offline && !navigator.onLine && (
        <Alert className="mb-3 flex items-center gap-2">
          <WifiOff className="size-4" aria-hidden="true" />
          Немає мережі. Відповідь буде надіслано, коли з’єднання відновиться.
        </Alert>
      )}
      {error && <Alert role="alert" className="mb-3">{error}</Alert>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="flex min-h-[70vh] flex-col">
          <div className="flex items-center justify-between gap-3 border-b border-slate-100 p-4">
            <div className="flex items-center gap-3">
              <span className="flex size-12 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
                <Laptop className="size-6" aria-hidden="true" />
              </span>
              <div>
                <p className="text-xs text-slate-500">Обрана професія</p>
                <p className="font-semibold text-slate-900">{profile.desired_title || TRACK_NAMES[profile.track] || profile.track}</p>
              </div>
            </div>
          </div>
          <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4" aria-live="polite" aria-label="Листування">
            {turns.map((t) => (
              <div key={t.id} className="flex flex-col gap-3">
                <div className="msg-in flex items-end gap-2 motion-reduce:animate-none">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600">
                    <Bot className="size-5" aria-hidden="true" />
                  </span>
                  <div className="max-w-[80%]">
                    <p className="rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-2.5 text-[15px] leading-relaxed text-slate-900">
                      <span className="sr-only">Питання: </span>
                      <BotText text={t.question_text} animate={animateIds.current.has(t.id)} />
                    </p>
                    <p className="mt-1 text-xs text-slate-400">{timeLabel(t.created_at)}</p>
                  </div>
                </div>
                {t.answer_text !== null && (
                  <div className="msg-in flex items-end justify-end gap-2 motion-reduce:animate-none">
                    <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2.5 text-[15px] leading-relaxed text-white">
                      <span className="sr-only">Ваша відповідь: </span>
                      {t.answer_text}
                    </p>
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white">
                      <UserIcon className="size-5" aria-hidden="true" />
                    </span>
                  </div>
                )}
              </div>
            ))}
            {optimistic && (
              <div className="msg-in flex items-end justify-end gap-2 motion-reduce:animate-none">
                <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2.5 text-[15px] text-white opacity-80">{optimistic}</p>
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white">
                  <UserIcon className="size-5" aria-hidden="true" />
                </span>
              </div>
            )}
            {(thinking || busy) && <TypingIndicator />}
            <div ref={endRef} />
          </div>
          {state?.status === 'PAUSED' && (
            <div className="border-t border-slate-100 p-4">
              <Button onClick={() => void lifecycle('resume')} disabled={busy}>
                <Play className="size-4" aria-hidden="true" />
                Продовжити розмову
              </Button>
            </div>
          )}
          {pending && state?.status === 'ACTIVE' && (
            <form onSubmit={send} className="border-t border-slate-100 p-3">
              <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 focus-within:border-blue-500">
                <label htmlFor="answer" className="sr-only">Ваша відповідь</label>
                <Textarea
                  id="answer"
                  ref={inputRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={onKeyDown}
                  maxLength={4000}
                  rows={2}
                  placeholder="Введіть вашу відповідь…"
                  className="min-h-12 resize-none border-0 shadow-none focus-visible:outline-0"
                />
                <Button type="submit" size="icon" disabled={busy || !draft.trim()} aria-label="Надіслати">
                  {busy ? <Loader2 className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Send className="size-5" aria-hidden="true" />}
                </Button>
              </div>
              <p className="mt-2 text-center text-xs text-slate-500">Enter — надіслати, Shift+Enter — новий рядок</p>
            </form>
          )}
        </Card>

        <aside className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Поточний профіль</CardTitle>
              <p className="text-sm text-slate-500">Виявлені компетентності за вашими відповідями.</p>
            </CardHeader>
            <CardContent>
              {!llmConfigured && (
                <Alert className="mb-3 text-xs">Автоматична оцінка зараз вимкнена, тому профіль не заповнюється.</Alert>
              )}
              {profileItems.length === 0 ? (
                <p className="text-sm text-slate-500">Оцінки з’являться після ваших відповідей.</p>
              ) : (
                <ul className="flex flex-col gap-4">
                  {profileItems.map((a) => <ScoreBar key={a.action_id} name={a.action_name} score={a.score ?? 0} />)}
                </ul>
              )}
            </CardContent>
          </Card>
          {pending && (
            <Card className="border-blue-100 bg-blue-50/60">
              <CardContent className="flex items-start gap-3 pt-5">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-white text-blue-600">
                  <Target className="size-6" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-xs text-blue-700">Поточна компетентність</p>
                  <p className="text-lg font-semibold text-slate-900">{pending.action_name}</p>
                  <p className="text-sm text-slate-600">Кілька запитань, щоб краще оцінити ваш досвід.</p>
                </div>
              </CardContent>
            </Card>
          )}
          <Card>
            <CardContent className="flex items-start gap-3 pt-5">
              <Lightbulb className="mt-0.5 size-5 shrink-0 text-amber-500" aria-hidden="true" />
              <div>
                <p className="font-semibold text-slate-900">Порада</p>
                <p className="text-sm text-slate-600">Наводьте конкретні приклади з вашого досвіду: це допомагає точніше оцінити рівень.</p>
              </div>
            </CardContent>
          </Card>
          <div className="flex flex-wrap gap-2">
            {state?.status === 'ACTIVE' && (
              <Button variant="outline" onClick={() => void lifecycle('pause')} disabled={busy}>
                <Pause className="size-4" aria-hidden="true" />
                Призупинити
              </Button>
            )}
            <Button variant="outline" onClick={() => void lifecycle('finish')} disabled={busy || turns.every((t) => t.answer_text === null)}>
              <Flag className="size-4" aria-hidden="true" />
              Завершити і переглянути результати
            </Button>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}
