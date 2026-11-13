import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { CheckCircle2, LockKeyhole, Pause, Play, Send, SkipForward, Sparkles, TrendingUp, WandSparkles } from 'lucide-react';
import { request, ApiError } from '../api';
import { uk } from '../i18n/uk';
import type { Evidence, Interview, LLMInfo, Turn } from '../types';
import { Card, EmptyState, Tag2, Bar, ErrorAlert } from '../components/ui';

type Props = {
  interview: Interview | null;
  llm: LLMInfo | null;
  labelFor: (id: string) => string;
  onChange: (next: Interview) => void;
  onRefresh: () => Promise<void>;
  onStart: () => void;
  onOpenResults: () => void;
};

const MAX_ANSWER = 4000;

function turnBadge(turn: Turn, ev: Evidence | undefined): { text: string; tone: 'green' | 'orange' | 'red' | 'grey' | 'blue' }[] {
  if (turn.status === 'SKIPPED') return [{ text: uk.interview.statusSkipped, tone: 'grey' }];
  if (turn.question_kind === 'MULTIPLE_CHOICE') {
    if (turn.assessment_status === 'DEMO_OBSERVED_LEVEL_1') return [{ text: uk.interview.checkPassed, tone: 'green' }];
    if (turn.assessment_status === 'INSUFFICIENT_EVIDENCE') return [{ text: uk.interview.checkFailed, tone: 'grey' }];
  }
  if (ev?.status === 'CONFIRMED') return [{ text: uk.interview.statusConfirmed, tone: 'green' }];
  if (ev?.status === 'REJECTED') return [{ text: uk.interview.statusRejected, tone: 'grey' }];
  if (ev?.status === 'PROPOSED') return [{ text: uk.interview.statusProposed, tone: 'orange' }];
  return [{ text: uk.interview.statusSaved, tone: 'blue' }, { text: uk.interview.statusPending, tone: 'orange' }];
}

export function InterviewScreen({ interview, llm, labelFor, onChange, onRefresh, onStart, onOpenResults }: Props) {
  const [draft, setDraft] = useState('');
  const [option, setOption] = useState('');
  const [sending, setSending] = useState(false);
  const [localError, setLocalError] = useState('');
  const [evidence, setEvidence] = useState<Record<string, Evidence>>({});
  const [gradingTurn, setGradingTurn] = useState<string | null>(null);
  const keyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!interview) return;
    let alive = true;
    request<Evidence[]>(`/interviews/${interview.id}/evidence`)
      .then(rows => { if (alive) setEvidence(Object.fromEntries(rows.map(r => [r.turn_id, r]))); })
      .catch(() => { /* evidence list is optional for rendering */ });
    return () => { alive = false; };
  }, [interview?.id]);

  if (!interview) {
    return <EmptyState title={uk.interview.none} text={uk.interview.noneText} action={uk.interview.start} onAction={onStart} />;
  }

  const current = interview.current_question;
  const total = interview.question_budget;
  const shown = Math.min(interview.used_questions, total);
  const completed = interview.status === 'COMPLETED';
  const paused = interview.status === 'PAUSED';
  const isChoice = current?.question_kind === 'MULTIPLE_CHOICE';

  async function run(action: () => Promise<void>) {
    setSending(true);
    setLocalError('');
    try { await action(); }
    catch (err) {
      setLocalError(err instanceof ApiError || err instanceof Error ? err.message : uk.common.genericError);
      if (err instanceof ApiError && (err.code === 'STALE_SESSION_VERSION' || err.status === 409)) await onRefresh();
    } finally { setSending(false); }
  }

  function submit() {
    if (!current) return;
    const body = {
      turn_id: current.id,
      state_version: interview!.state_version,
      idempotency_key: keyRef.current ?? (keyRef.current = crypto.randomUUID()),
      ...(isChoice ? { option_id: option } : { answer_text: draft.trim() }),
    };
    void run(async () => {
      let result = await request<Interview>(`/interviews/${interview!.id}/answers`, 'POST', body);
      keyRef.current = null;
      setDraft(''); setOption('');
      if (result.status === 'READY') {
        result = await request<Interview>(`/interviews/${interview!.id}/next-question`, 'POST', { state_version: result.state_version });
      }
      onChange(result);
    });
  }

  function nextQuestion() {
    void run(async () => onChange(await request<Interview>(`/interviews/${interview!.id}/next-question`, 'POST', { state_version: interview!.state_version })));
  }

  function skip() {
    if (!current) return;
    void run(async () => {
      let result = await request<Interview>(`/interviews/${interview!.id}/skip`, 'POST', { turn_id: current.id, state_version: interview!.state_version });
      if (result.status === 'READY') result = await request<Interview>(`/interviews/${interview!.id}/next-question`, 'POST', { state_version: result.state_version });
      setDraft(''); setOption('');
      onChange(result);
    });
  }

  function control(action: 'pause' | 'resume' | 'finish') {
    void run(async () => onChange(await request<Interview>(`/interviews/${interview!.id}/${action}`, 'POST', { state_version: interview!.state_version })));
  }

  function grade(turnId: string) {
    setGradingTurn(turnId);
    void run(async () => {
      const ev = await request<Evidence>(`/interviews/${interview!.id}/turns/${turnId}/grade`, 'POST');
      setEvidence(prev => ({ ...prev, [turnId]: ev }));
    }).finally(() => setGradingTurn(null));
  }

  function review(ev: Evidence, decision: 'ACCEPT' | 'REJECT') {
    void run(async () => {
      const updated = await request<Evidence>(`/evidence/${ev.id}/review`, 'POST', { decision });
      setEvidence(prev => ({ ...prev, [updated.turn_id]: updated }));
      await onRefresh();
    });
  }

  function onAnswerKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && canSubmit) { e.preventDefault(); submit(); }
  }

  const canSubmit = !sending && (isChoice ? option !== '' : draft.trim().length > 0);

  return (
    <div className="interview-grid">
      <Card className="chat-card">
        <div className="interview-lead">
          <div>
            <Tag2 tone="blue">{uk.interview.title}</Tag2>
            <p className="muted" aria-live="polite">{uk.interview.progress(shown, total)}</p>
          </div>
          <Bar value={total ? shown / total : 0} label={uk.interview.progress(shown, total)} />
        </div>
        <p className="muted provider-line">
          {llm?.question_generation ? uk.interview.providerLlm : uk.interview.providerBank}
        </p>

        <ol className="chat-history" aria-label="Історія інтервю">
          {interview.turns.map(turn => {
            const ev = evidence[turn.id];
            const answered = turn.status === 'ANSWERED';
            const canGrade = Boolean(llm?.configured) && answered && turn.question_kind === 'FREE_TEXT' && !ev && !completed;
            return (
              <li key={turn.id} className="chat-turn">
                <div className="bubble bot-bubble">
                  <small>{turn.question_source === 'LLM_GENERATED' ? uk.interview.sourceGenerated : uk.interview.sourceBank} · {labelFor(turn.competency_id)}</small>
                  {turn.question_format === 'OPTIONAL_CHECK' && <small className="check-badge">{uk.interview.optionalCheck}</small>}
                  <p>{turn.question_text}</p>
                </div>
                {(answered || turn.status === 'SKIPPED') && (
                  <div className="bubble user-bubble">
                    {turn.status === 'SKIPPED' ? uk.interview.statusSkipped : (turn.answer_text ?? turn.question_options.find(o => o.id === turn.answer_option)?.text ?? '—')}
                  </div>
                )}
                <div className="badge-row">
                  {turnBadge(turn, ev).map(b => <Tag2 key={b.text} tone={b.tone}>{b.text}</Tag2>)}
                </div>
                {canGrade && (
                  <button className="btn ghost small" disabled={sending} onClick={() => grade(turn.id)} aria-busy={gradingTurn === turn.id}>
                    <WandSparkles size={15} aria-hidden="true" /> {gradingTurn === turn.id ? uk.interview.gradeBusy : uk.interview.gradeButton}
                  </button>
                )}
                {ev && (
                  <div className="evidence-box" aria-label="Пропозиція оцінки">
                    <p>{ev.level !== null ? uk.interview.proposedLevel(ev.level) : uk.interview.proposedNone}</p>
                    {ev.evidence_quote && <blockquote><small>{uk.interview.quoteLabel}:</small> {ev.evidence_quote}</blockquote>}
                    {ev.uncertainty && <p className="muted"><small>{uk.interview.uncertaintyLabel}: {ev.uncertainty === 'NO_SUPPORTING_QUOTE' ? uk.interview.noQuote : ev.uncertainty}</small></p>}
                    <p className="muted"><small>{uk.interview.gradeNote}</small></p>
                    {ev.status === 'PROPOSED' && (
                      <div className="answer-controls">
                        <button className="btn primary small" disabled={sending || ev.level === null} onClick={() => review(ev, 'ACCEPT')}>{uk.interview.accept}</button>
                        <button className="btn ghost small" disabled={sending} onClick={() => review(ev, 'REJECT')}>{uk.interview.reject}</button>
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ol>

        {completed && (
          <div className="completed-banner" role="status"><CheckCircle2 size={24} aria-hidden="true" /><div><strong>{uk.interview.completed}</strong></div></div>
        )}
        {paused && <div className="paused-banner" role="status"><Pause size={22} aria-hidden="true" />{uk.interview.paused}</div>}
        {localError && <ErrorAlert message={localError} onDismiss={() => setLocalError('')} onRetry={current ? submit : undefined} />}

        {!completed && !paused && interview.status === 'WAITING_FOR_ANSWER' && current && (
          <form className="answer-area" onSubmit={e => { e.preventDefault(); if (canSubmit) submit(); }}>
            {isChoice ? (
              <fieldset className="answer-options">
                <legend>{uk.interview.optionalCheck}</legend>
                <p className="muted">{uk.interview.optionalHint}</p>
                {current.question_options.map(opt => (
                  <label key={opt.id} className={`answer-choice ${option === opt.id ? 'chosen' : ''}`}>
                    <input type="radio" name="option" value={opt.id} checked={option === opt.id} onChange={() => setOption(opt.id)} />
                    <span>{opt.text}</span>
                  </label>
                ))}
              </fieldset>
            ) : (
              <div className="field">
                <label htmlFor="answer-text">{uk.interview.answerLabel}</label>
                <textarea id="answer-text" rows={5} maxLength={MAX_ANSWER} aria-describedby="answer-hint answer-count"
                  value={draft} disabled={sending}
                  onChange={e => { setDraft(e.target.value); keyRef.current = null; }} onKeyDown={onAnswerKey} />
                <div className="answer-meta">
                  <small id="answer-hint" className="muted">{uk.interview.answerHint}</small>
                  <small id="answer-count" className="muted">{uk.interview.charCount(draft.length)}</small>
                </div>
              </div>
            )}
            <div className="answer-controls">
              <button type="button" className="btn ghost small" onClick={skip} disabled={sending}><SkipForward size={16} aria-hidden="true" />{uk.interview.skip}</button>
              <button type="submit" className="btn primary" disabled={!canSubmit}>
                <Send size={17} aria-hidden="true" />{sending ? uk.interview.sending : isChoice ? uk.interview.optionSubmit : uk.interview.send}
              </button>
            </div>
          </form>
        )}

        {!completed && !paused && interview.status === 'READY' && !current && (
          <div className="answer-controls">
            {shown >= total
              ? <button className="btn primary" onClick={() => control('finish')} disabled={sending}><CheckCircle2 size={16} aria-hidden="true" />{uk.interview.finishReady}</button>
              : <button className="btn primary" onClick={nextQuestion} disabled={sending}><Sparkles size={16} aria-hidden="true" />{uk.interview.nextQuestion}</button>}
          </div>
        )}

        <div className="chat-footer">
          {paused && <button className="btn primary" disabled={sending} onClick={() => control('resume')}><Play size={16} aria-hidden="true" />{uk.interview.resume}</button>}
          {completed && <button className="btn primary" onClick={onOpenResults}><TrendingUp size={17} aria-hidden="true" />{uk.interview.results}</button>}
          {!completed && !paused && (
            <>
              <span className="muted"><LockKeyhole size={14} aria-hidden="true" /> Набір вакансій зафіксовано</span>
              <div>
                <button className="btn ghost small" disabled={sending} onClick={() => control('pause')}><Pause size={14} aria-hidden="true" />{uk.interview.pause}</button>
                <button className="btn ghost small" disabled={sending} onClick={() => control('finish')}>{uk.interview.finish}</button>
              </div>
            </>
          )}
        </div>
      </Card>

      <aside className="interview-sidebar" aria-label={uk.interview.currentProfile}>
        <Card>
          <h3>{uk.interview.currentProfile}</h3>
          <p className="muted">{uk.interview.profileHint}</p>
          <ul className="mini-skills">
            {Object.entries(interview.effective_profile.levels).filter(([, v]) => v !== null).slice(0, 10).map(([id, lev]) => (
              <li key={id}>
                <div><strong>{labelFor(id)}</strong><span>{uk.interview.level(lev as number)}</span></div>
                <Bar value={((lev as number) ?? 0) / 3} tone={lev === 3 ? 'green' : 'blue'} label={labelFor(id)} />
              </li>
            ))}
          </ul>
        </Card>
      </aside>
    </div>
  );
}
