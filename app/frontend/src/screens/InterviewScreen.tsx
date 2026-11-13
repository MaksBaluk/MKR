import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { api, ApiError } from '@/api';
import { Alert } from '@/components/ui/alert';
import { Avatar } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { timeLabel } from '@/lib/bands';
import { MAX_TOPICS, PANEL_TEXT as P, deriveTopics, topicsCountLabel } from '@/lib/interviewTopics';
import type { InterviewState, Profile, TurnView } from '@/types';
import { Bot, CheckCircle2, ChevronDown, Circle, Flag, Info, Laptop, Lightbulb, Loader2, Pause, Play, Send, Target, WifiOff } from 'lucide-react';

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
      <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary">
        <Bot className="size-5" aria-hidden="true" />
      </span>
      <div className="flex gap-1 rounded-2xl rounded-bl-sm bg-surface-muted px-4 py-3">
        {[0, 1, 2].map((i) => (
          <span key={i} className="typing-dot size-2 rounded-full bg-ink-subtle motion-reduce:animate-none"
            style={{ animationDelay: `${i * 0.16}s` }} />
        ))}
      </div>
    </div>
  );
}

export function InterviewScreen({ interviewId, profile, llmConfigured, onFinished }: {
  interviewId: string;
  profile: Profile;
  llmConfigured: boolean;
  onFinished: () => void;
}) {
  const [state, setState] = useState<InterviewState | null>(null);
  const [pending, setPending] = useState<TurnView | null>(null);
  const [infoOpen, setInfoOpen] = useState(false);
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
  const topicList = deriveTopics(turns);

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-5">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
            <Laptop className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-xs text-ink-subtle">Професія для оцінювання</p>
            <p className="truncate font-semibold text-ink">{profile.desired_title || TRACK_NAMES[profile.track] || profile.track}</p>
          </div>
        </div>
        <div className="flex w-full items-center gap-3 sm:w-auto">
          <Progress value={(topics / MAX_TOPICS) * 100} label="Прогрес розмови" className="flex-1 sm:w-44" />
          <span className="shrink-0 text-sm font-medium tabular-nums text-ink-muted">{topicsCountLabel(topics)}</span>
        </div>
      </Card>
      {offline && !navigator.onLine && (
        <Alert icon={false} className="items-center">
          <WifiOff className="mr-2 inline size-4 align-[-2px]" aria-hidden="true" />
          Немає мережі. Відповідь буде надіслано, коли з’єднання відновиться.
        </Alert>
      )}
      {error && <Alert role="alert" variant="danger">{error}</Alert>}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="flex min-h-[70vh] flex-col">
          <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4" aria-live="polite" aria-label="Листування">
            {turns.map((t) => (
              <div key={t.id} className="flex flex-col gap-3">
                <div className="msg-in flex items-end gap-2 motion-reduce:animate-none">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary">
                    <Bot className="size-5" aria-hidden="true" />
                  </span>
                  <div className="max-w-[80%]">
                    <p className="rounded-2xl rounded-bl-sm bg-surface-muted px-4 py-2.5 text-[15px] leading-relaxed text-ink">
                      <span className="sr-only">Питання: </span>
                      <BotText text={t.question_text} animate={animateIds.current.has(t.id)} />
                    </p>
                    <p className="mt-1 text-xs text-ink-subtle">{timeLabel(t.created_at)}</p>
                  </div>
                </div>
                {t.answer_text !== null && (
                  <div className="msg-in flex items-end justify-end gap-2 motion-reduce:animate-none">
                    <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-[15px] leading-relaxed text-on-primary">
                      <span className="sr-only">Ваша відповідь: </span>
                      {t.answer_text}
                    </p>
                    <Avatar name={profile.display_name} className="size-9 text-xs" />
                  </div>
                )}
              </div>
            ))}
            {optimistic && (
              <div className="msg-in flex items-end justify-end gap-2 motion-reduce:animate-none">
                <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-[15px] text-on-primary opacity-80">{optimistic}</p>
                <Avatar name={profile.display_name} className="size-9 text-xs" />
              </div>
            )}
            {(thinking || busy) && <TypingIndicator />}
            <div ref={endRef} />
          </div>
          {state?.status === 'PAUSED' && (
            <div className="border-t border-line p-4">
              <Button onClick={() => void lifecycle('resume')} disabled={busy}>
                <Play className="size-4" aria-hidden="true" />
                Продовжити розмову
              </Button>
            </div>
          )}
          {pending && state?.status === 'ACTIVE' && (
            <form onSubmit={send} className="border-t border-line p-3">
              <div className="flex items-end gap-2 rounded-2xl border border-line bg-white p-2 focus-within:border-primary">
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
              <p className="mt-2 text-center text-xs text-ink-subtle">Enter — надіслати, Shift+Enter — новий рядок</p>
            </form>
          )}
        </Card>

        <aside className="flex flex-col gap-4">
          <button
            type="button"
            className="flex items-center justify-between rounded-xl border border-line bg-white px-4 py-3 text-left font-semibold text-ink lg:hidden"
            aria-expanded={infoOpen}
            aria-controls="interview-info"
            onClick={() => setInfoOpen((v) => !v)}
          >
            <span className="flex items-center gap-2"><Info className="size-5 text-primary" aria-hidden="true" />{P.disclosure}</span>
            <ChevronDown className={`size-5 transition-transform motion-reduce:transition-none ${infoOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
          </button>
          <div id="interview-info" className={`${infoOpen ? 'flex' : 'hidden'} flex-col gap-4 lg:flex`}>
            <Card>
              <CardHeader>
                <CardTitle>{P.topicsTitle}</CardTitle>
                <p className="text-sm text-ink-subtle">{topicsCountLabel(topics)}. {P.topicsNote}</p>
              </CardHeader>
              <CardContent>
                {topicList.length === 0 ? (
                  <p className="text-sm text-ink-subtle">{P.topicsEmpty}</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {topicList.map((tp) => (
                      <li key={tp.action_id} className="flex items-center gap-2 text-sm text-ink">
                        {tp.isCurrent
                          ? <Circle className="size-4 shrink-0 text-primary" aria-hidden="true" />
                          : <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />}
                        <span className="min-w-0 flex-1 truncate">{tp.action_name}</span>
                        {tp.isCurrent && <span className="rounded-full bg-primary-soft px-2 py-0.5 text-xs text-primary">{P.currentMarker}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            {pending && (
              <Card className="border-primary-line bg-primary-soft">
                <CardContent className="flex items-start gap-3 pt-5">
                  <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-white text-primary">
                    <Target className="size-6" aria-hidden="true" />
                  </span>
                  <div>
                    <p className="text-xs text-primary">{P.currentTopic}</p>
                    <p className="text-lg font-semibold text-ink">{pending.action_name}</p>
                    <p className="text-sm text-ink-muted">{P.currentTopicLine}</p>
                  </div>
                </CardContent>
              </Card>
            )}
            <Card>
              <CardContent className="flex items-start gap-3 pt-5">
                <Lightbulb className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden="true" />
                <div>
                  <p className="font-semibold text-ink">{P.tipsTitle}</p>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-ink-muted">
                    {P.tips.map((tip) => <li key={tip}>{tip}</li>)}
                  </ul>
                </div>
              </CardContent>
            </Card>
            {!llmConfigured && (
              <Alert className="text-sm">{P.llmOff}</Alert>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {state?.status === 'ACTIVE' && (
              <Button variant="outline" onClick={() => void lifecycle('pause')} disabled={busy}>
                <Pause className="size-4" aria-hidden="true" />
                {P.pause}
              </Button>
            )}
            <Button variant="outline" onClick={() => void lifecycle('finish')} disabled={busy || turns.every((t) => t.answer_text === null)}>
              <Flag className="size-4" aria-hidden="true" />
              {P.finish}
            </Button>
          </div>
        </aside>
      </div>
    </div>
  );
}
