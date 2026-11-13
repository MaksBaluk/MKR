import { useEffect, useState } from 'react';
import { api, ApiError } from '@/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { SelfRatingList } from '@/components/SelfRatingList';
import type { AssessmentItem, MarketSkill, Profile, RankedItem } from '@/types';
import { Briefcase, Info, LogOut, RefreshCw } from 'lucide-react';

type Tab = 'recommendations' | 'market' | 'assessments' | 'profile';

interface RankedResponse {
  items: (RankedItem & { title: string; company: string; location: string; work_mode: string })[];
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

export function ResultsScreen({ cohortId, onLogout, onProfileChanged }: {
  cohortId: string;
  onLogout: () => void;
  onProfileChanged: () => void;
}) {
  const [tab, setTab] = useState<Tab>('recommendations');
  const [ranked, setRanked] = useState<RankedResponse | null>(null);
  const [market, setMarket] = useState<MarketSkill[] | null>(null);
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

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Результати</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
            <RefreshCw className="size-4" aria-hidden="true" />
            Оновити
          </Button>
          <Button variant="ghost" size="sm" onClick={onLogout}>
            <LogOut className="size-4" aria-hidden="true" />
            Вийти
          </Button>
        </div>
      </header>
      <Alert role="note" className="flex gap-2 border-blue-200 bg-blue-50 text-blue-900">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        Порядок вакансій детермінований і базується на відповідях у розмові. Це не ймовірність працевлаштування.
      </Alert>
      {error && <Alert role="alert">{error}</Alert>}
      {loading && <p role="status" className="text-sm text-slate-600">Завантаження результатів…</p>}
      <div role="tablist" aria-label="Розділи результатів" className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-blue-600 ${
              tab === t.id ? 'bg-blue-600 text-white' : 'bg-white text-slate-700 hover:bg-slate-100'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'recommendations' && (
        <section role="tabpanel" id="panel-recommendations" aria-labelledby="tab-recommendations" className="flex flex-col gap-3">
          {ranked?.items.map((item) => (
            <Card key={item.vacancy_id}>
              <CardHeader className="flex-row items-start justify-between gap-3">
                <div className="flex flex-col gap-1">
                  <CardTitle className="text-base">{item.title}</CardTitle>
                  <p className="text-sm text-slate-600">{item.company} · {item.location}</p>
                </div>
                <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-[#1c1c1c] px-2 py-1 text-xs font-semibold text-white">
                  <Briefcase className="size-3" aria-hidden="true" />
                  Джерело: Djinni
                </span>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                <p>{mandatoryText(item.z)}</p>
                {item.label === 'LOW_INFORMATION' && (
                  <Badge variant="warning">Недостатньо відповідей для висновку</Badge>
                )}
                {item.label === 'NOT_EVALUABLE' && <Badge variant="warning">Вимоги не розпізнано</Badge>}
              </CardContent>
            </Card>
          ))}
          {ranked && ranked.items.length === 0 && <p className="text-sm text-slate-600">Вакансій за вашим треком ще немає.</p>}
        </section>
      )}

      {tab === 'market' && (
        <section role="tabpanel" id="panel-market" aria-labelledby="tab-market">
          <Card>
            <CardHeader>
              <CardTitle>Професійні дії у вибраній добірці</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-sm text-slate-600">
                Порядок за поширеністю в добірці. Це лише вибірка з каталогу, а не дані про ринок праці.
              </p>
              <ol className="flex flex-col gap-2">
                {market?.map((s) => (
                  <li key={s.action_id} className="flex items-center gap-3 rounded-md border border-slate-200 p-2 text-sm">
                    <span className="w-8 text-slate-500">{s.order}.</span>
                    <span className="font-medium">{s.name}</span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </section>
      )}

      {tab === 'assessments' && (
        <section role="tabpanel" id="panel-assessments" aria-labelledby="tab-assessments">
          <Card>
            <CardHeader>
              <CardTitle>Оцінки розмови</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="text-sm text-slate-600">Оцінки можна лише переглядати. Вони описують ваші відповіді, а не перевірений досвід.</p>
              {assessments?.length === 0 && <p className="text-sm text-slate-600">Оцінок ще немає: відповіді без автоматичної оцінки.</p>}
              <ul className="flex flex-col gap-2">
                {assessments?.map((a) => (
                  <li key={`${a.interview_id}-${a.action_id}-${a.revision}`} className="rounded-md border border-slate-200 p-3 text-sm">
                    <p className="font-medium">{a.action_id}</p>
                    <p>Оцінка: {a.score === null ? 'недостатньо свідчень' : a.score.toFixed(2)}</p>
                    <p className="text-slate-600">{a.reason}</p>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>
      )}

      {tab === 'profile' && profile && (
        <section role="tabpanel" id="panel-profile" aria-labelledby="tab-profile">
          <Card>
            <CardHeader>
              <CardTitle>Самооцінка</CardTitle>
            </CardHeader>
            <CardContent>
              <SelfRatingList
                track={profile.track}
                initial={Object.fromEntries(profile.self_ratings.map((r) => [r.action_id, r.value]))}
                onSaved={onProfileChanged}
              />
            </CardContent>
          </Card>
        </section>
      )}
    </main>
  );
}
