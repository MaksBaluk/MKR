import { useCallback, useEffect, useMemo, useState } from 'react';
import { BriefcaseBusiness, LayoutGrid, LogOut, MessageSquareText, Settings, Target, TrendingUp, UserRound } from 'lucide-react';
import { request, setToken, token, ApiError } from './api';
import { uk } from './i18n/uk';
import type { Interview, LLMInfo, MatchRun, Profile, Recommendations, Skill, Snapshot, Track } from './types';
import { AuthScreen } from './screens/AuthScreen';
import { RecommendationsScreen, noFilters, type RecFilters } from './screens/RecommendationsScreen';
import { InterviewScreen } from './screens/InterviewScreen';
import { ResultsScreen } from './screens/ResultsScreen';
import { CatalogScreen } from './screens/CatalogScreen';
import { ProfileScreen, type ProfileDraft } from './screens/ProfileScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { VacancyModal } from './components/VacancyModal';
import { ErrorAlert, Notice } from './components/ui';

type View = 'recs' | 'interview' | 'results' | 'catalog' | 'profile' | 'settings';

const menu: { id: View; text: string; icon: typeof LayoutGrid }[] = [
  { id: 'recs', text: uk.nav.recommendations, icon: LayoutGrid },
  { id: 'interview', text: uk.nav.interview, icon: MessageSquareText },
  { id: 'results', text: uk.nav.results, icon: TrendingUp },
  { id: 'catalog', text: uk.nav.catalog, icon: BriefcaseBusiness },
  { id: 'profile', text: uk.nav.profile, icon: UserRound },
  { id: 'settings', text: uk.nav.settings, icon: Settings },
];

const initials = (name: string) => name.trim().slice(0, 2).toUpperCase();

export default function App() {
  const [view, setView] = useState<View>('recs');
  const [booting, setBooting] = useState(true);
  const [account, setAccount] = useState<Profile | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [llm, setLlm] = useState<LLMInfo | null>(null);
  const [demoMode, setDemoMode] = useState(false);
  const [recs, setRecs] = useState<Recommendations | null>(null);
  const [filters, setFilters] = useState<RecFilters>(noFilters);
  const [interview, setInterview] = useState<Interview | null>(null);
  const [baseline, setBaseline] = useState<MatchRun | null>(null);
  const [after, setAfter] = useState<MatchRun | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const labelFor = useMemo(() => {
    const map = new Map(skills.map(s => [s.id, s.label_uk]));
    return (id: string) => map.get(id) ?? id;
  }, [skills]);

  const fail = (err: unknown) => setError(err instanceof Error ? err.message : uk.common.genericError);

  async function act(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); }
    catch (err) { fail(err); }
    finally { setBusy(false); }
  }

  const loadRecs = useCallback(async (f: RecFilters) => {
    const params = new URLSearchParams();
    if (f.work_mode) params.set('work_mode', f.work_mode);
    if (f.seniority) params.set('seniority', f.seniority);
    if (f.location.trim()) params.set('location', f.location.trim());
    if (f.respect_experience) params.set('respect_experience', 'true');
    setRecs(await request<Recommendations>(`/discovery/recommendations?${params}`));
  }, []);

  const loadSession = useCallback(async () => {
    const profile = await request<Profile>('/profile');
    setAccount(profile);
    const [skillRows, snaps, interviews, matches] = await Promise.all([
      request<Skill[]>(`/competencies?track=${profile.track}`),
      request<Snapshot[]>('/snapshots'),
      request<Interview[]>('/interviews'),
      request<{ id: string; snapshot_id: string; interview_id: string | null }[]>('/matches'),
    ]);
    setSkills(skillRows);
    await loadRecs(noFilters);
    // Only the current track's sets are shown; a running interview from another track is not resumed.
    const trackSnapIds = new Set(snaps.filter(sn => sn.track === profile.track).map(sn => sn.id));
    const trackInterviews = interviews.filter(iv => trackSnapIds.has(iv.snapshot_id));
    const latestSnap = snaps.find(sn => sn.track === profile.track) ?? null;
    const latestInterview = trackInterviews[0] ? await request<Interview>(`/interviews/${trackInterviews[0].id}`) : null;
    setInterview(latestInterview);
    const cohortId = latestInterview?.snapshot_id ?? latestSnap?.id;
    const runs = matches.filter(m => m.snapshot_id === cohortId);
    const baseRow = runs.find(m => !m.interview_id);
    const afterRow = latestInterview ? runs.find(m => m.interview_id === latestInterview.id) : undefined;
    setBaseline(baseRow ? await request<MatchRun>(`/matches/${baseRow.id}`) : null);
    setAfter(afterRow ? await request<MatchRun>(`/matches/${afterRow.id}`) : null);
    // Resume: an unfinished interview reopens on its own screen after login or reload.
    setView(latestInterview && latestInterview.status !== 'COMPLETED' ? 'interview' : 'recs');
  }, [loadRecs]);

  useEffect(() => {
    (async () => {
      try {
        const config = await request<{ demo_mode: boolean; llm: LLMInfo }>('/config');
        setDemoMode(config.demo_mode);
        setLlm(config.llm);
      } catch (err) { fail(err); }
      if (token()) {
        try { await loadSession(); }
        catch (err) { if (err instanceof ApiError && err.status === 401) setToken(null); else fail(err); }
      }
      setBooting(false);
    })();
  }, [loadSession]);

  function resetWorkspace() {
    setInterview(null); setBaseline(null); setAfter(null);
  }

  function logout() {
    setToken(null); setAccount(null); resetWorkspace(); setRecs(null); setView('recs'); setError(''); setNotice('');
  }

  async function authenticate(mode: 'login' | 'register', data: { email: string; password: string; name: string }) {
    await act(async () => {
      const result = mode === 'register'
        ? await request<{ token: string }>('/auth/register', 'POST', { email: data.email, display_name: data.name, password: data.password })
        : await request<{ token: string }>('/auth/login', 'POST', { email: data.email, password: data.password });
      setToken(result.token);
      await loadSession();
    });
  }

  async function demoLogin() {
    await act(async () => {
      const result = await request<{ token: string }>('/auth/demo', 'POST');
      setToken(result.token);
      await loadSession();
    });
  }

  async function applyFilters(next: RecFilters) {
    setFilters(next);
    await act(() => loadRecs(next));
  }

  async function startInterview() {
    if (interview && interview.status !== 'COMPLETED') { setView('interview'); return; }
    await act(async () => {
      const snap = await request<Snapshot>('/discovery/snapshots', 'POST', {
        name: 'Рекомендовані вакансії',
        work_mode: filters.work_mode || null,
        seniority: filters.seniority || null,
        location_contains: filters.location.trim() || null,
        respect_experience: filters.respect_experience,
      });
      const created = await request<Interview>('/interviews', 'POST', { snapshot_id: snap.id });
      const first = await request<Interview>(`/interviews/${created.id}/next-question`, 'POST', { state_version: created.state_version });
      setInterview(first);
      setAfter(null);
      if (snap.baseline_match_id) setBaseline(await request<MatchRun>(`/matches/${snap.baseline_match_id}`));
      setView('interview');
    });
  }

  async function refreshInterview() {
    if (!interview) return;
    setInterview(await request<Interview>(`/interviews/${interview.id}`));
  }

  async function openResults() {
    if (!interview) { setView('results'); return; }
    await act(async () => {
      if (!after && interview.status === 'COMPLETED') {
        setAfter(await request<MatchRun>('/matches', 'POST', { snapshot_id: interview.snapshot_id, interview_id: interview.id }));
      }
      setView('results');
    });
  }

  async function saveProfile(draft: ProfileDraft) {
    if (!account) return;
    await act(async () => {
      const updated = await request<Profile>('/profile', 'PUT', {
        display_name: draft.display_name, desired_title: draft.desired_title,
        years_experience: draft.years_experience, location: draft.location, track: draft.track,
      });
      const trackChanged = updated.track !== account.track;
      setAccount(updated);
      if (trackChanged) {
        resetWorkspace();
        setSkills(await request<Skill[]>(`/competencies?track=${updated.track}`));
        await loadRecs(noFilters);
      }
      setNotice(uk.profile.saved);
    });
  }

  async function saveSkill(id: string, level: number | null) {
    await act(async () => {
      await request(`/profile/skills/${id}`, 'PUT', { level, context: '' });
      setAccount(await request<Profile>('/profile'));
    });
  }

  async function deleteData() {
    await act(async () => {
      await request('/profile/data', 'DELETE');
      resetWorkspace();
      await loadSession();
      setNotice(uk.settings.deleted);
    });
  }

  if (booting) {
    return <div className="auth-shell"><p className="muted" role="status">{uk.common.loading}</p></div>;
  }

  if (!account) {
    return <AuthScreen busy={busy} error={error} demoMode={demoMode}
      onSubmit={authenticate} onDemo={() => void demoLogin()} onDismissError={() => setError('')} />;
  }

  const trackTitle = uk.tracks[account.track as Track];
  const titles: Record<View, string> = {
    recs: uk.recs.title, interview: uk.interview.title, results: uk.results.title,
    catalog: uk.catalog.title, profile: uk.profile.title, settings: uk.settings.title,
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Перейти до змісту</a>
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="brand-logo small"><Target size={22} aria-hidden="true" /></div>
          <span className="brand-name">Competence<span>Match</span></span>
        </div>
        <nav aria-label="Основна навігація" className="nav-items">
          {menu.map(m => {
            const Icon = m.icon;
            const current = view === m.id;
            return (
              <button key={m.id} className={`nav-item ${current ? 'active' : ''}`} aria-label={m.text} aria-current={current ? 'page' : undefined} onClick={() => setView(m.id)}>
                <Icon size={19} aria-hidden="true" /><span>{m.text}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="user-strip">
            <div className="avatar" aria-hidden="true">{initials(account.display_name)}</div>
            <div><strong>{account.display_name}</strong><small>{trackTitle}</small></div>
            <button className="icon-button" aria-label={uk.nav.logout} title={uk.nav.logout} onClick={logout}><LogOut size={17} aria-hidden="true" /></button>
          </div>
        </div>
      </aside>

      <div className="main-content">
        <header className="topbar">
          <div className="title-area">
            <span className="breadcrumbs">{uk.brand} <span aria-hidden="true">/</span> {trackTitle}</span>
            <h1>{titles[view]}</h1>
          </div>
        </header>
        <main id="main" className="workspace" tabIndex={-1}>
          {error && <ErrorAlert message={error} onDismiss={() => setError('')} />}
          {notice && view !== 'settings' && <Notice message={notice} onDismiss={() => setNotice('')} />}

          {view === 'recs' && (
            <RecommendationsScreen recs={recs} busy={busy} filters={filters} onFilters={f => void applyFilters(f)}
              onStart={() => void startInterview()} onOpenVacancy={setDetailId}
              activeInterview={Boolean(interview && interview.status !== 'COMPLETED')}
              onResume={() => setView('interview')} />
          )}
          {view === 'interview' && (
            <InterviewScreen interview={interview} llm={llm} labelFor={labelFor}
              onChange={setInterview} onRefresh={refreshInterview}
              onStart={() => void startInterview()} onOpenResults={() => void openResults()} />
          )}
          {view === 'results' && (
            <ResultsScreen baseline={baseline} after={after} labelFor={labelFor}
              onOpenVacancy={setDetailId} onBack={() => setView('recs')} />
          )}
          {view === 'catalog' && <CatalogScreen track={account.track} onOpenVacancy={setDetailId} />}
          {view === 'profile' && (
            <ProfileScreen profile={account} skills={skills} busy={busy}
              onSave={saveProfile} onSkill={saveSkill} />
          )}
          {view === 'settings' && (
            <SettingsScreen llm={llm} busy={busy} notice={notice} onDismissNotice={() => setNotice('')} onDeleteData={deleteData} />
          )}
        </main>
      </div>

      {detailId && <VacancyModal vacancyId={detailId} labelFor={labelFor} onClose={() => setDetailId(null)} />}
    </div>
  );
}
