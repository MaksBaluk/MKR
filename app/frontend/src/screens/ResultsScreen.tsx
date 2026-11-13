import { useEffect, useState } from 'react';
import { api, ApiError } from '@/api';
import { AppShell } from '@/components/AppShell';
import { ScoreBar } from '@/components/ScoreBar';
import { SelfRatingList } from '@/components/SelfRatingList';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { AssessmentItem, MarketSkill, Profile, RankedItem } from '@/types';
import { CheckCircle2, ChevronDown, FileText, HelpCircle, Info, MapPin, MinusCircle, RefreshCw } from 'lucide-react';

type Tab = 'recommendations' | 'market' | 'assessments' | 'profile';
type Ranked = RankedItem & { title: string; company: string; location: string; work_mode: string };
interface RankedResponse {
  items: Ranked[];
  total: number;
  assessed_actions: number;
  note: string;
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'recommendations', label: 'Рекомендації' },
  { id: 'market', label: 'Профіль ринку' },
  { id: 'assessments', label: 'Оцінки розмови' },
  { id: 'profile', label: 'Мій профіль' },
];

function mandatoryText(z: number): string {
  if (z === 2) return 'Обов’язкові вимоги підтверджено відповідями';
  if (z === 0) return 'Є обов’язкова вимога, яку відповіді не підтвердили';
  return 'Частину обов’язкових вимог ще не оцінено';
}

function SourceMark() {
  return (
    <span className="flex size-14 shrink-0 flex-col items-center justify-center rounded-xl bg-[#1c1c1c] text-white" title="Джерело: Djinni">
      <span className="text-2xl font-bold leading-none">d</span>
    </span>
  );
}

function VacancyCard({ item, rank }: { item: Ranked; rank: number }) {
  const [open, setOpen] = useState(false);
  const lowInfo = item.label === 'LOW_INFORMATION';
  return (
    <Card>
      <div className="flex flex-wrap items-start gap-4 p-4">
        <span className="flex size-10 items-center justify-center rounded-lg bg-blue-50 font-semibold text-blue-700">{rank}</span>
        <SourceMark />
        <div className="min-w-0 flex-1 basis-60">
          <h3 className="text-base font-semibold text-slate-900">{item.title}</h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-slate-600">
            <span>{item.company}</span>
            <span className="text-slate-300">·</span>
            <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" aria-hidden="true" />{item.location}</span>
          </p>
          <p className="mt-0.5 text-xs text-slate-500">Джерело: Djinni</p>
          <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Ключові технології">
            {item.tags.map((t) => <li key={t}><Badge variant="info">{t}</Badge></li>)}
          </ul>
        </div>
        <div className="w-full shrink-0 sm:w-56">
          <p className="text-xs text-slate-500">Підтверджено відповідями</p>
          <p className="text-2xl font-bold tabular-nums text-blue-700">{item.confirmed_share}%</p>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`Підтверджено відповідями: ${item.confirmed_share}%`}>
            <div className="h-full rounded-full bg-blue-600 transition-[width] duration-700 motion-reduce:transition-none"
              style={{ width: `${item.confirmed_share}%` }} />
          </div>
          <p className="mt-1 text-[11px] leading-snug text-slate-500">Нижня межа за оціненими вимогами. Це не ймовірність працевлаштування.</p>
          <Button variant="outline" size="sm" className="mt-3 w-full" aria-expanded={open} onClick={() => setOpen(!open)}>
            Деталі
            <ChevronDown className={`size-4 transition-transform motion-reduce:transition-none ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
          </Button>
        </div>
      </div>
      {open && (
        <div className="msg-in grid gap-4 border-t border-slate-100 p-4 text-sm sm:grid-cols-3 motion-reduce:animate-none">
          <div>
            <p className="mb-1 flex items-center gap-1.5 font-semibold text-emerald-700"><CheckCircle2 className="size-4" aria-hidden="true" />Підтверджено</p>
            {item.strengths.length ? <ul className="list-disc pl-5 text-slate-700">{item.strengths.map((s) => <li key={s}>{s}</li>)}</ul>
              : <p className="text-slate-500">Поки немає</p>}
          </div>
          <div>
            <p className="mb-1 flex items-center gap-1.5 font-semibold text-amber-700"><MinusCircle className="size-4" aria-hidden="true" />Прогалини</p>
            {item.gaps.length ? <ul className="list-disc pl-5 text-slate-700">{item.gaps.map((s) => <li key={s}>{s}</li>)}</ul>
              : <p className="text-slate-500">Не виявлено</p>}
          </div>
          <div>
            <p className="mb-1 flex items-center gap-1.5 font-semibold text-slate-700"><HelpCircle className="size-4" aria-hidden="true" />Не оцінено</p>
            <p className="text-slate-700">Вимог без оцінки: {item.unknown_count}</p>
            <p className="mt-1 text-slate-500">{mandatoryText(item.z)}</p>
            {lowInfo && <Badge variant="warning" className="mt-2">Недостатньо відповідей для висновку</Badge>}
          </div>
        </div>
      )}
    </Card>
  );
}

export function ResultsScreen({ cohortId, name, onLogout, onProfileChanged }: {
  cohortId: string;
  name: string;
  onLogout: () => void;
  onProfileChanged: () => void;
}) {
  const [tab, setTab] = useState<Tab>('recommendations');
  const [ranked, setRanked] = useState<RankedResponse | null>(null);
  const [market, setMarket] = useState<MarketSkill[] | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [assessments, setAssessments] = useState<AssessmentItem[] | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [r, m, a, p] = await Promise.all([
        api<RankedResponse>('/recommendations', { method: 'POST', json: { cohort_id: cohortId } }),
        api<{ skills: MarketSkill[] }>(`/cohorts/${cohortId}/market`),
        api<{ items: AssessmentItem[] }>('/assessments'),
        api<Profile>('/profile'),
      ]);
      setRanked(r);
      setMarket(m.skills);
      setAssessments(a.items);
      setProfile(p);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не вдалося завантажити результати. Спробуйте ще раз.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // load on mount and when cohort changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cohortId]);

  const latest = new Map<string, AssessmentItem>();
  assessments?.forEach((a) => {
    if (a.score !== null) latest.set(a.action_id, a);
  });
  const scored = [...latest.values()].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const visibleMarket = showAll ? market : market?.slice(0, 5);

  return (
    <AppShell
      title="Результати співбесіди"
      name={name}
      onLogout={onLogout}
      right={
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={`size-4 ${loading ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden="true" />
          Оновити
        </Button>
      }
    >
      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_auto]">
        <Alert role="note" className="flex gap-2 border-blue-200 bg-blue-50 text-blue-900">
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          Порядок вакансій детермінований і базується на ваших відповідях. Відсоток показує лише частку вимог, підтверджену
          відповідями, і не є ймовірністю працевлаштування.
        </Alert>
        <Card className="flex items-center gap-4 px-4 py-3">
          <span className="flex size-11 items-center justify-center rounded-xl bg-blue-50 text-blue-600"><FileText className="size-6" aria-hidden="true" /></span>
          <dl className="text-sm">
            <div className="flex gap-2"><dt className="text-slate-500">Проаналізовано вакансій:</dt><dd className="font-bold">{ranked?.total ?? '—'}</dd></div>
            <div className="flex gap-2"><dt className="text-slate-500">Оцінено компетентностей:</dt><dd className="font-bold">{ranked?.assessed_actions ?? '—'}</dd></div>
          </dl>
        </Card>
      </div>
      {error && <Alert role="alert" className="mb-3">{error}</Alert>}
      {loading && <p role="status" className="mb-3 text-sm text-slate-600">Завантаження результатів…</p>}
      <div role="tablist" aria-label="Розділи результатів" className="mb-4 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button key={t.id} role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id} aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-blue-600 ${
              tab === t.id ? 'bg-blue-600 text-white shadow-sm' : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'recommendations' && (
        <section role="tabpanel" id="panel-recommendations" aria-labelledby="tab-recommendations" className="flex flex-col gap-3">
          <p className="text-sm text-slate-600">Топ-{ranked?.items.length ?? 5} найрелевантніших вакансій із {ranked?.total ?? '—'}.</p>
          {ranked?.items.map((item, i) => <VacancyCard key={item.vacancy_id} item={item} rank={i + 1} />)}
          {ranked && ranked.items.length === 0 && <p className="text-sm text-slate-600">Вакансій за вашим треком ще немає.</p>}
        </section>
      )}

      {tab === 'market' && (
        <section role="tabpanel" id="panel-market" aria-labelledby="tab-market">
          <Card>
            <CardHeader><CardTitle>Найпоширеніші професійні дії в добірці</CardTitle></CardHeader>
            <CardContent>
              <p className="mb-3 text-sm text-slate-600">Порядок за поширеністю в добірці. Це вибірка з каталогу, а не дані про ринок праці.</p>
              <ol className="flex flex-col gap-2">
                {visibleMarket?.map((s) => (
                  <li key={s.action_id} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 text-sm">
                    <span className="flex size-7 items-center justify-center rounded-md bg-blue-50 font-semibold text-blue-700">{s.order}</span>
                    <span className="font-medium">{s.name}</span>
                  </li>
                ))}
              </ol>
              {market && market.length > 5 && (
                <Button variant="ghost" size="sm" className="mt-3" onClick={() => setShowAll(!showAll)}>
                  {showAll ? 'Показати лише 5' : `Показати всі (${market.length})`}
                </Button>
              )}
            </CardContent>
          </Card>
        </section>
      )}

      {tab === 'assessments' && (
        <section role="tabpanel" id="panel-assessments" aria-labelledby="tab-assessments">
          <Card>
            <CardHeader><CardTitle>Поточний профіль</CardTitle></CardHeader>
            <CardContent>
              <p className="mb-4 text-sm text-slate-600">Оцінки можна лише переглядати. Вони описують ваші відповіді, а не перевірений досвід.</p>
              {scored.length === 0 ? (
                <p className="text-sm text-slate-600">Оцінок ще немає: автоматична оцінка не змогла опрацювати відповіді.</p>
              ) : (
                <ul className="grid gap-5 sm:grid-cols-2">
                  {scored.slice(0, 5).map((a) => (
                    <div key={a.action_id}>
                      <ScoreBar name={a.action_name} score={a.score ?? 0} />
                      <p className="mt-2 text-xs text-slate-600">{a.reason}</p>
                    </div>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </section>
      )}

      {tab === 'profile' && profile && (
        <section role="tabpanel" id="panel-profile" aria-labelledby="tab-profile">
          <Card>
            <CardHeader><CardTitle>Самооцінка</CardTitle></CardHeader>
            <CardContent>
              <SelfRatingList track={profile.track}
                initial={Object.fromEntries(profile.self_ratings.map((r) => [r.action_id, r.value]))}
                onSaved={onProfileChanged} />
            </CardContent>
          </Card>
        </section>
      )}
    </AppShell>
  );
}
