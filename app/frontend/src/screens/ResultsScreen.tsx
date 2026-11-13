import { useState } from 'react';
import { ArrowRight, ChevronDown } from 'lucide-react';
import { uk } from '../i18n/uk';
import type { MatchRun } from '../types';
import { formatPercent } from '../format';
import { Card, EmptyState, Tag2 } from '../components/ui';
import { MatchHeadline, RequirementsList } from '../components/MatchMetrics';
import { summarize } from '../domain/presentation';

type Props = {
  baseline: MatchRun | null; after: MatchRun | null; labelFor: (id: string) => string;
  onOpenVacancy: (id: string) => void; onBack: () => void;
};

function diffLabel(baseRank: number | null | undefined, afterRank: number | null): { text: string; tone: 'green' | 'red' | 'grey' | 'blue' } {
  if (baseRank === undefined) return { text: uk.results.diffNew, tone: 'blue' };
  if (baseRank === null || afterRank === null) return { text: uk.results.diffSame, tone: 'grey' };
  if (afterRank < baseRank) return { text: uk.results.diffUp(baseRank - afterRank), tone: 'green' };
  if (afterRank > baseRank) return { text: uk.results.diffDown(afterRank - baseRank), tone: 'red' };
  return { text: uk.results.diffSame, tone: 'grey' };
}

export function ResultsScreen({ baseline, after, labelFor, onOpenVacancy, onBack }: Props) {
  const [tab, setTab] = useState<'base' | 'after'>(after ? 'after' : 'base');
  const [open, setOpen] = useState<string | null>(null);
  const run = tab === 'after' && after ? after : baseline;

  if (!baseline && !after) {
    return <EmptyState title={uk.results.emptyTitle} text={uk.results.emptyText} action={uk.results.back} onAction={onBack} />;
  }

  const baseRanks = new Map((baseline?.items ?? []).map(i => [i.vacancy_id, i.rank_position]));
  const unchanged = tab === 'after' && after?.unchanged_reason === 'NO_ACCEPTED_EVIDENCE';

  return (
    <>
      <div role="tablist" aria-label={uk.results.title} className="tabs">
        <button role="tab" aria-selected={tab === 'base'} className={`tab ${tab === 'base' ? 'active' : ''}`} onClick={() => setTab('base')} disabled={!baseline}>{uk.results.tabBase}</button>
        <button role="tab" aria-selected={tab === 'after'} className={`tab ${tab === 'after' ? 'active' : ''}`} onClick={() => setTab('after')} disabled={!after}>{uk.results.tabAfter}</button>
      </div>
      {run && (
        <>
          <div className="results-toolbar">
            <span>{tab === 'after' ? uk.results.profileAfter : uk.results.profileBase}</span>
            <Tag2 tone="grey">{run.total} вакансій</Tag2>
          </div>
          {unchanged && <p className="rank-note" role="status">{uk.results.unchanged}</p>}
          <p className="muted">{uk.results.hint}</p>
          <ol className="results-list" aria-label={uk.results.title}>
            {run.items.map(item => {
              const diff = tab === 'after' ? diffLabel(baseRanks.get(item.vacancy_id), item.rank_position) : null;
              const isOpen = open === item.vacancy_id;
              return (
                <li key={item.vacancy_id}>
                  <Card className="result-card" as="article">
                    <div className="result-summary">
                      <div className="result-index">{item.rank_position ?? '—'}</div>
                      <div className="result-info">
                        <h3 className="result-name">{item.vacancy.title}</h3>
                        <div className="meta-line"><span>{item.vacancy.company}</span></div>
                        <p className="headline-line"><strong>{summarize(item).headline}</strong> <span className="muted">· {summarize(item).coverageLabel} · {summarize(item).unknownLabel}</span></p>
                        {diff && <Tag2 tone={diff.tone}>{diff.text}</Tag2>}
                      </div>
                      <div className="result-metrics">
                        <div><small>R</small><strong>{formatPercent(item.r_score)}</strong></div>
                        <div><small>{uk.metrics.coverage}</small><strong>{formatPercent(item.coverage)}</strong></div>
                      </div>
                      <button className="btn ghost small" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : item.vacancy_id)}>
                        {isOpen ? uk.common.close : uk.recs.details} <ChevronDown size={16} className={isOpen ? 'rotated' : ''} aria-hidden="true" />
                      </button>
                      <button className="btn ghost small" onClick={() => onOpenVacancy(item.vacancy_id)}>Вакансія <ArrowRight size={14} aria-hidden="true" /></button>
                    </div>
                    {isOpen && (
                      <div className="result-details">
                        <MatchHeadline row={item} />
                        <h4>{uk.metrics.groupsTitle}</h4>
                        <RequirementsList groups={item.groups} labelFor={labelFor} />
                      </div>
                    )}
                  </Card>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </>
  );
}
