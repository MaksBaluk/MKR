import { useEffect, useRef, useState } from 'react';
import { BriefcaseBusiness, X } from 'lucide-react';
import { request, ApiError } from '../api';
import { uk } from '../i18n/uk';
import type { Vacancy } from '../types';
import { formatSalary } from '../format';
import { Tag2, EmptyState, ErrorAlert } from './ui';

export function VacancyModal({ vacancyId, labelFor, onClose }: { vacancyId: string; labelFor: (id: string) => string; onClose: () => void }) {
  const [vacancy, setVacancy] = useState<Vacancy | null>(null);
  const [error, setError] = useState('');
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let alive = true;
    setError('');
    request<Vacancy>(`/vacancies/${vacancyId}`)
      .then(v => { if (alive) setVacancy(v); })
      .catch(err => { if (alive) setError(err instanceof ApiError ? err.message : uk.common.genericError); });
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => { alive = false; window.removeEventListener('keydown', onKey); };
  }, [vacancyId, onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="vacancy-modal-title" onClick={e => e.stopPropagation()}>
        <button ref={closeRef} className="icon-button modal-close" aria-label={uk.modal.closeLabel} onClick={onClose}><X size={21} aria-hidden="true" /></button>
        {error && <ErrorAlert message={error} onDismiss={() => setError('')} />}
        {!vacancy && !error && <p className="muted">{uk.common.loading}</p>}
        {vacancy && (
          <>
            <div className="modal-kicker"><BriefcaseBusiness size={18} aria-hidden="true" />{vacancy.company} <span aria-hidden="true">/</span>{uk.locations[vacancy.location] ?? vacancy.location}</div>
            <h2 id="vacancy-modal-title">{vacancy.title}</h2>
            <div className="modal-tags">
              <Tag2>{uk.seniority[vacancy.seniority as keyof typeof uk.seniority] ?? vacancy.seniority}</Tag2>
              <Tag2 tone="green">{uk.workMode[vacancy.work_mode as keyof typeof uk.workMode] ?? vacancy.work_mode}</Tag2>
              <Tag2 tone="grey">{formatSalary(vacancy.salary_min, vacancy.salary_max, vacancy.currency)}</Tag2>
            </div>
            <p className="provenance-note">{uk.catalog.provenance}</p>
            <div className="modal-body">
              <h3>{uk.modal.description}</h3>
              <p className="description-pre">{vacancy.description}</p>
              <h3>{uk.modal.requirements(vacancy.groups?.length ?? 0)}</h3>
              {vacancy.groups?.length ? vacancy.groups.map(g => (
                <div key={g.id} className="modal-requirement">
                  <Tag2 tone={g.kind === 'MANDATORY' ? 'blue' : 'grey'}>{g.kind === 'MANDATORY' ? uk.metrics.mandatory : uk.metrics.desired}</Tag2>
                  <span>{g.label}</span>
                  <small>{g.alternatives.map(a => `${labelFor(a.competency_id)}: ${a.required_level}/3`).join(' або ')}</small>
                </div>
              )) : <EmptyState title="Вимог немає" text="Для цієї вакансії не задано структурованих вимог." />}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
