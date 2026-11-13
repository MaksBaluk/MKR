import { Check, CircleHelp, X } from 'lucide-react';
import { summarize, type MatchRow } from '../domain/presentation';
import { formatPercent } from '../format';
import { uk } from '../i18n/uk';
import { Bar, Tag2 } from './ui';

/** Shows the backend metrics with honest labels. Match is conditional; R and Coverage lead. */
export function MatchHeadline({ row }: { row: MatchRow }) {
  const s = summarize(row);
  return (
    <div className="metric-headline">
      <p className="metric-main"><strong>{s.headline}</strong></p>
      <div className="metric-chips" aria-label="Підсумок вимог">
        <Tag2 tone="green">{uk.metrics.s}: {row.s}</Tag2>
        <Tag2 tone="red">{uk.metrics.f}: {row.f}</Tag2>
        <Tag2 tone="grey">{s.unknownLabel}</Tag2>
        <Tag2 tone={s.mandatoryTone}>{s.mandatoryLabel}</Tag2>
      </div>
      <div className="metric-grid">
        <div><small>{uk.metrics.r}</small><strong>{formatPercent(row.r_score)}</strong><Bar value={row.r_score} label={uk.metrics.r} /></div>
        <div><small>{uk.metrics.coverage}</small><strong>{formatPercent(row.coverage)}</strong><Bar value={row.coverage} tone="green" label={uk.metrics.coverage} /></div>
        <div><small>{uk.metrics.match}</small><strong className="muted-value">{s.matchLabel}</strong></div>
      </div>
      <p className="metric-hint">{uk.metrics.unknownNote}</p>
    </div>
  );
}

export function RequirementsList({ groups, labelFor }: {
  groups: { id: string; kind: string; label: string; state: 'S' | 'F' | 'U'; alternatives: { competency_id: string; required_level: number }[] }[];
  labelFor: (id: string) => string;
}) {
  return (
    <ul className="requirements-grid" aria-label={uk.metrics.groupsTitle}>
      {groups.map(g => (
        <li key={g.id} className={`requirement-line state-${g.state}`}>
          <span className={`state-dot dot-${g.state}`} aria-hidden="true">
            {g.state === 'S' ? <Check size={14} /> : g.state === 'F' ? <X size={14} /> : <CircleHelp size={14} />}
          </span>
          <div>
            <strong>{g.label}</strong>
            <small>
              {g.kind === 'MANDATORY' ? uk.metrics.mandatory : uk.metrics.desired}: {g.alternatives.map(a => `${labelFor(a.competency_id)} ≥ ${a.required_level}`).join(' або ')}
            </small>
          </div>
          <span className="state-word">{g.state === 'S' ? uk.metrics.s : g.state === 'F' ? uk.metrics.f : uk.metrics.u}</span>
        </li>
      ))}
    </ul>
  );
}
