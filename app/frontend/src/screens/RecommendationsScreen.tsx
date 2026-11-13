import { useState } from 'react';
import { ArrowRight, Lightbulb } from 'lucide-react';
import { uk } from '../i18n/uk';
import type { Recommendations } from '../types';
import { formatPercent, formatSalary } from '../format';
import { Card, EmptyState, Tag2 } from '../components/ui';
import { MatchHeadline } from '../components/MatchMetrics';
import { summarize } from '../domain/presentation';

export type RecFilters = { work_mode: string; seniority: string; location: string; respect_experience: boolean };
export const noFilters: RecFilters = { work_mode: '', seniority: '', location: '', respect_experience: false };

export function RecommendationsScreen({ recs, busy, filters, onFilters, onStart, onOpenVacancy, activeInterview, onResume }: {
  recs: Recommendations | null; busy: boolean; filters: RecFilters; onFilters: (f: RecFilters) => void;
  onStart: () => void; onOpenVacancy: (id: string) => void;
  activeInterview: boolean; onResume: () => void;
}) {
  const [draft, setDraft] = useState<RecFilters>(filters);

  if (!recs) return <p className="muted">{uk.common.loading}</p>;

  return (
    <>
      <div className="intro-line">
        <div>
          <h2>{uk.recs.subtitle}</h2>
          <p>{uk.recs.intro}</p>
          <p className="muted">{uk.recs.evidence(recs.evidence_quality.assessed_competencies, recs.evidence_quality.total_competencies)}</p>
        </div>
        <Tag2 tone="green">{uk.tracks[recs.track]}</Tag2>
      </div>

      <form className="toolbar filters" aria-label={uk.recs.filters} onSubmit={e => { e.preventDefault(); onFilters(draft); }}>
        <div className="field">
          <label htmlFor="f-mode">Формат роботи</label>
          <select id="f-mode" value={draft.work_mode} onChange={e => setDraft({ ...draft, work_mode: e.target.value })}>
            <option value="">{uk.recs.anyMode}</option>
            {Object.entries(uk.workMode).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="f-seniority">{uk.catalog.seniority}</label>
          <select id="f-seniority" value={draft.seniority} onChange={e => setDraft({ ...draft, seniority: e.target.value })}>
            <option value="">{uk.recs.rankedFilter}</option>
            {Object.entries(uk.seniority).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="f-location">{uk.recs.location}</label>
          <select id="f-location" value={draft.location} onChange={e => setDraft({ ...draft, location: e.target.value })}>
            <option value="">Будь-яке місто</option>
            {Object.entries(uk.locations).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </div>
        <label className="check-row">
          <input type="checkbox" checked={draft.respect_experience} onChange={e => setDraft({ ...draft, respect_experience: e.target.checked })} />
          {uk.recs.respectExperience}
        </label>
        <div className="filter-actions">
          <button className="btn ghost small" type="button" onClick={() => { setDraft(noFilters); onFilters(noFilters); }}>{uk.recs.reset}</button>
          <button className="btn primary small" type="submit" disabled={busy}>{uk.recs.apply}</button>
        </div>
      </form>

      <p className="rank-note"><Lightbulb size={16} aria-hidden="true" /> {uk.recs.rankingNote}</p>

      {recs.total === 0 ? (
        <EmptyState title="Вакансій не знайдено" text={uk.recs.empty} />
      ) : (
        <ol className="results-list" aria-label="Рекомендовані вакансії">
          {recs.items.map(item => (
            <li key={item.vacancy_id}>
              <Card className="result-card" as="article">
                <div className="result-summary">
                  <div className="result-index" aria-label={item.rank_position ? uk.recs.rank(item.rank_position) : uk.recs.unranked}>{item.rank_position ?? '—'}</div>
                  <div className="result-info">
                    <h3 className="result-name">{item.vacancy.title}</h3>
                    <div className="meta-line">
                      <span>{item.vacancy.company}</span><span className="dot-sep" aria-hidden="true" />
                      <span>{uk.locations[item.vacancy.location] ?? item.vacancy.location}</span><span className="dot-sep" aria-hidden="true" />
                      <span>{uk.seniority[item.vacancy.seniority as keyof typeof uk.seniority]}</span>
                    </div>
                    <p>{item.vacancy.summary}</p>
                    <p className="headline-line"><strong>{summarize(item).headline}</strong> <span className="muted">· {summarize(item).coverageLabel} · {summarize(item).unknownLabel}</span></p>
                  </div>
                  <div className="result-side">
                    <strong>{formatSalary(item.vacancy.salary_min, item.vacancy.salary_max, item.vacancy.currency)}</strong>
                    <small>{summarize(item).coverageLabel} · R: {formatPercent(item.r_score)}</small>
                    <button className="btn ghost small" onClick={() => onOpenVacancy(item.vacancy_id)} aria-label={`${uk.recs.details}: ${item.vacancy.title}`}>
                      {uk.recs.details} <ArrowRight size={14} aria-hidden="true" />
                    </button>
                  </div>
                </div>
                <details className="result-details">
                  <summary>Пояснення відповідності</summary>
                  <MatchHeadline row={item} />
                </details>
              </Card>
            </li>
          ))}
        </ol>
      )}

      <div className="selection-bar">
        <div><strong>{uk.recs.startHint}</strong></div>
        {activeInterview ? (
          <button className="btn primary" onClick={onResume}>Продовжити інтервю <ArrowRight size={17} aria-hidden="true" /></button>
        ) : (
          <button disabled={busy || recs.total === 0} className="btn primary" onClick={onStart}>
            {uk.recs.startAll(recs.total)} <ArrowRight size={17} aria-hidden="true" />
          </button>
        )}
      </div>
    </>
  );
}
