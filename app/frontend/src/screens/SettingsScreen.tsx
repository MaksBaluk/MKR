import { useEffect, useState } from 'react';
import { BookOpen, ExternalLink, ShieldCheck, WandSparkles } from 'lucide-react';
import { request, ApiError } from '../api';
import { uk } from '../i18n/uk';
import type { LLMInfo } from '../types';
import { Card, ErrorAlert, Notice, Tag2 } from '../components/ui';

export function SettingsScreen({ llm, busy, onDeleteData, notice, onDismissNotice }: {
  llm: LLMInfo | null; busy: boolean; onDeleteData: () => Promise<void>; notice: string; onDismissNotice: () => void;
}) {
  const [counts, setCounts] = useState<{ vacancies: number | null; competencies: number | null }>({ vacancies: null, competencies: null });
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([request<{ total: number }>('/vacancies?page_size=1'), request<unknown[]>('/competencies')])
      .then(([v, c]) => setCounts({ vacancies: v.total, competencies: c.length }))
      .catch(err => setError(err instanceof ApiError ? err.message : uk.common.genericError));
  }, []);

  return (
    <>
      <div className="intro-line"><div><h2>{uk.settings.title}</h2></div></div>
      {notice && <Notice message={notice} onDismiss={onDismissNotice} />}
      {error && <ErrorAlert message={error} onDismiss={() => setError('')} />}

      <div className="settings-grid">
        <Card>
          <h3><WandSparkles size={20} aria-hidden="true" /> {uk.settings.llm}</h3>
          <div className="setting-row"><span>{uk.settings.llmStatus}</span><Tag2 tone={llm?.configured ? 'green' : 'orange'}>{llm?.configured ? uk.settings.llmOn : uk.settings.llmOff}</Tag2></div>
          <div className="setting-row"><span>{uk.settings.provider}</span><strong>{llm?.provider ?? 'disabled'}</strong></div>
          <div className="setting-row"><span>{uk.settings.model}</span><strong>{llm?.model ?? '—'}</strong></div>
          <div className="setting-row"><span>{uk.settings.generation}</span><strong>{llm?.question_generation ? uk.settings.genOn : uk.settings.genOff}</strong></div>
          <p className="subtle-notice"><ShieldCheck size={16} aria-hidden="true" />{uk.settings.llmNote}</p>
        </Card>
        <Card>
          <h3><BookOpen size={20} aria-hidden="true" /> {uk.settings.catalog}</h3>
          <div className="setting-row"><span>{uk.settings.catalogVacancies}</span><strong>{counts.vacancies ?? '—'}</strong></div>
          <div className="setting-row"><span>{uk.settings.catalogCompetencies}</span><strong>{counts.competencies ?? '—'}</strong></div>
          <p className="subtle-notice">{uk.catalog.provenance}</p>
        </Card>
      </div>

      <Card>
        <h3>{uk.settings.api}</h3>
        <p className="muted">{uk.settings.apiText}</p>
        <div className="about-actions">
          <a className="btn ghost" href="/docs" target="_blank" rel="noreferrer">Swagger UI <ExternalLink size={14} aria-hidden="true" /></a>
          <a className="btn ghost" href="/openapi.json" target="_blank" rel="noreferrer">OpenAPI JSON <ExternalLink size={14} aria-hidden="true" /></a>
        </div>
      </Card>

      <Card className="danger-card">
        <h3>{uk.settings.danger}</h3>
        <p className="muted">{uk.settings.dangerText}</p>
        <button className="btn danger" disabled={busy}
          onClick={() => { if (window.confirm(uk.settings.dangerConfirm)) void onDeleteData(); }}>
          {uk.settings.dangerBtn}
        </button>
      </Card>
    </>
  );
}
