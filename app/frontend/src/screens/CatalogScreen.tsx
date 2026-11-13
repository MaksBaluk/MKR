import { useEffect, useState } from 'react';
import { ArrowRight, Search } from 'lucide-react';
import { request, ApiError } from '../api';
import { uk } from '../i18n/uk';
import type { Vacancy } from '../types';
import { formatSalary } from '../format';
import { Card, EmptyState, ErrorAlert, Tag2 } from '../components/ui';

const PAGE = 12;

export function CatalogScreen({ track, onOpenVacancy }: { track: string; onOpenVacancy: (id: string) => void }) {
  const [query, setQuery] = useState('');
  const [seniority, setSeniority] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<Vacancy[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true); setError('');
    const params = new URLSearchParams({ track, page: String(page), page_size: String(PAGE) });
    if (query.trim()) params.set('q', query.trim());
    if (seniority) params.set('seniority', seniority);
    request<{ items: Vacancy[]; total: number }>(`/vacancies?${params}`)
      .then(res => { if (alive) { setItems(res.items); setTotal(res.total); } })
      .catch(err => { if (alive) setError(err instanceof ApiError ? err.message : uk.common.genericError); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [track, query, seniority, page, reload]);

  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <>
      <div className="intro-line">
        <div>
          <h2>{uk.catalog.subtitle}</h2>
          <p>{uk.catalog.intro}</p>
        </div>
        <Tag2 tone="green">{uk.catalog.total(total)}</Tag2>
      </div>

      <Card className="toolbar">
        <div className="field grow">
          <label htmlFor="cat-q">{uk.catalog.search}</label>
          <div className="searchbox"><Search size={19} aria-hidden="true" />
            <input id="cat-q" type="search" value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="cat-seniority">{uk.catalog.seniority}</label>
          <select id="cat-seniority" value={seniority} onChange={e => { setSeniority(e.target.value); setPage(1); }}>
            <option value="">{uk.catalog.any}</option>
            {Object.entries(uk.seniority).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </div>
      </Card>

      {error && <ErrorAlert message={error} onDismiss={() => setError('')} onRetry={() => setReload(n => n + 1)} />}
      {loading && <p className="muted" role="status">{uk.common.loading}</p>}
      {!loading && !error && items.length === 0 && <EmptyState title="Нічого не знайдено" text={uk.catalog.empty} />}

      <ul className="vacancies-list" aria-label={uk.catalog.title}>
        {items.map(v => (
          <li key={v.id}>
            <Card className="vacancy-card" as="article">
              <div className="vacancy-info">
                <div className="vacancy-top">
                  <h3>{v.title}</h3>
                  <Tag2 tone={v.seniority === 'JUNIOR' ? 'green' : v.seniority === 'LEAD' ? 'orange' : 'blue'}>{uk.seniority[v.seniority as keyof typeof uk.seniority]}</Tag2>
                </div>
                <div className="meta-line">
                  <span>{v.company}</span><span className="dot-sep" aria-hidden="true" />
                  <span>{uk.locations[v.location] ?? v.location}</span><span className="dot-sep" aria-hidden="true" />
                  <span>{uk.workMode[v.work_mode as keyof typeof uk.workMode] ?? v.work_mode}</span>
                </div>
                <p>{v.summary}</p>
              </div>
              <div className="vacancy-actions">
                <strong>{formatSalary(v.salary_min, v.salary_max, v.currency)}</strong>
                <button className="btn ghost small" onClick={() => onOpenVacancy(v.id)} aria-label={`${uk.recs.details}: ${v.title}`}>
                  {uk.recs.details} <ArrowRight size={14} aria-hidden="true" />
                </button>
              </div>
            </Card>
          </li>
        ))}
      </ul>

      <nav className="pager" aria-label="Сторінки каталогу">
        <button className="btn ghost small" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>{uk.catalog.prev}</button>
        <span aria-live="polite">{uk.catalog.page(page, pages)}</span>
        <button className="btn ghost small" disabled={page >= pages} onClick={() => setPage(p => p + 1)}>{uk.catalog.next}</button>
      </nav>
      <p className="provenance-note">{uk.catalog.provenance}</p>
    </>
  );
}
