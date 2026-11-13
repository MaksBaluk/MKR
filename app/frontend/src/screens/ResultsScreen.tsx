import { useEffect, useState } from 'react';
import { api, ApiError } from '@/api';
import { ScoreBar } from '@/components/ScoreBar';
import { SelfRatingList } from '@/components/SelfRatingList';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs } from '@/components/ui/tabs';
import type { AssessmentItem, MarketSkill, Profile, RankedItem } from '@/types';
import { Building2, CheckCircle2, ChevronDown, FileText, HelpCircle, MapPin, MinusCircle, RefreshCw } from 'lucide-react';

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

function CompanyMark() {
  return (
    <span className="flex size-14 shrink-0 items-center justify-center rounded-2xl border border-line bg-canvas text-ink-subtle">
      <Building2 className="size-6" aria-hidden="true" />
    </span>
  );
}

function VacancyCard({ item, rank }: { item: Ranked; rank: number }) {
  const [open, setOpen] = useState(false);
  const lowInfo = item.label === 'LOW_INFORMATION';
  return (
    <Card>
      <div className="flex flex-wrap items-start gap-4 p-4">
        <span className="flex size-10 items-center justify-center rounded-lg bg-primary-soft font-semibold text-primary">{rank}</span>
        <CompanyMark />
        <div className="min-w-0 flex-1 basis-60">
          <h3 className="text-base font-semibold text-ink">{item.title}</h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-ink-muted">
            <span>{item.company}</span>
            <span className="text-line-strong">·</span>
            <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" aria-hidden="true" />{item.location}</span>
          </p>
          <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Ключові технології">
            {item.tags.map((t) => <li key={t}><Badge variant="info">{t}</Badge></li>)}
          </ul>
        </div>
        <div className="w-full shrink-0 sm:w-56">
          <p className="text-xs text-ink-subtle">Підтверджено відповідями</p>
          <p className="text-2xl font-bold tabular-nums text-primary">{item.confirmed_share}%</p>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-surface-muted" role="img" aria-label={`Підтверджено відповідями: ${item.confirmed_share}%`}>
            <div className="h-full rounded-full bg-primary transition-[width] duration-700 motion-reduce:transition-none"
              style={{ width: `${item.confirmed_share}%` }} />
          </div>
          <p className="mt-1 text-xs leading-snug text-ink-subtle">Нижня межа за оціненими вимогами. Це не ймовірність працевлаштування.</p>
          <Button variant="outline" size="sm" className="mt-3 w-full" aria-expanded={open} onClick={() => setOpen(!open)}>
            Деталі
            <ChevronDown className={`size-4 transition-transform motion-reduce:transition-none ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
          </Button>
        </div>
      </div>
      {open && (
        <div className="msg-in grid gap-4 border-t border-line p-4 text-sm sm:grid-cols-3 motion-reduce:animate-none">
          <div>
            <p className="mb-1 flex items-center gap-1.5 font-semibold text-success-ink"><CheckCircle2 className="size-4" aria-hidden="true" />Підтверджено</p>
            {item.strengths.length ? <ul className="list-disc pl-5 text-ink-muted">{item.strengths.map((s) => <li key={s}>{s}</li>)}</ul>
              : <p className="text-ink-subtle">Поки немає</p>}
          </div>
          <div>
            <p className="mb-1 flex items-center gap-1.5 font-semibold text-warning-ink"><MinusCircle className="size-4" aria-hidden="true" />Прогалини</p>
            {item.gaps.length ? <ul className="list-disc pl-5 text-ink-muted">{item.gaps.map((s) => <li key={s}>{s}</li>)}</ul>
              : <p className="text-ink-subtle">Не виявлено</p>}
          </div>
          <div>
            <p className="mb-1 flex items-center gap-1.5 font-semibold text-ink-muted"><HelpCircle className="size-4" aria-hidden="true" />Не оцінено</p>
            <p className="text-ink-muted">Вимог без оцінки: {item.unknown_count}</p>
            <p className="mt-1 text-ink-subtle">{mandatoryText(item.z)}</p>
            {lowInfo && <Badge variant="warning" className="mt-2">Недостатньо відповідей для висновку</Badge>}
          </div>
        </div>
      )}
    </Card>
  );
}

export function ResultsScreen({ cohortId, onProfileChanged }: {
  cohortId: string;
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
    <div className="flex flex-col gap-5">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,28rem)]">
        <Card className="flex flex-wrap items-center gap-4 p-5">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary text-on-primary">
            <FileText className="size-6" aria-hidden="true" />
          </span>
          <dl className="grid min-w-0 flex-1 grid-cols-2 gap-4">
            <div>
              <dt className="text-xs text-ink-subtle">Проаналізовано вакансій</dt>
              <dd className="text-2xl font-bold tabular-nums text-ink">{ranked?.total ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-subtle">Оцінено компетентностей</dt>
              <dd className="text-2xl font-bold tabular-nums text-ink">{ranked?.assessed_actions ?? '—'}</dd>
            </div>
          </dl>
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading} className="hidden sm:inline-flex">
            <RefreshCw className={`size-4 ${loading ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden="true" />
            Оновити
          </Button>
        </Card>
        <Alert role="note" variant="info">
          Порядок вакансій детермінований і базується на ваших відповідях. Відсоток показує лише частку вимог, підтверджену
          відповідями, і не є ймовірністю працевлаштування. Вакансії каталогу синтетичні.
        </Alert>
      </div>
      <Button variant="outline" onClick={() => void load()} disabled={loading} className="sm:hidden">
        <RefreshCw className={`size-4 ${loading ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden="true" />
        Оновити результати
      </Button>
      {error && <Alert role="alert" variant="danger">{error}</Alert>}
      <p role="status" className="sr-only">{loading ? 'Завантаження результатів…' : ''}</p>
      <Tabs items={TABS} value={tab} onChange={setTab} label="Розділи результатів" className="self-start" />

      {tab === 'recommendations' && (
        <section role="tabpanel" id="panel-recommendations" aria-labelledby="tab-recommendations" className="flex flex-col gap-3">
          <p className="text-sm text-ink-muted">Топ-{ranked?.items.length ?? 5} найрелевантніших вакансій із {ranked?.total ?? '—'}.</p>
          {loading && !ranked && [0, 1, 2].map((i) => <Skeleton key={i} className="h-36" />)}
          {ranked?.items.map((item, i) => <VacancyCard key={item.vacancy_id} item={item} rank={i + 1} />)}
          {ranked && ranked.items.length === 0 && <p className="text-sm text-ink-muted">Вакансій за вашим треком ще немає.</p>}
        </section>
      )}

      {tab === 'market' && (
        <section role="tabpanel" id="panel-market" aria-labelledby="tab-market">
          <Card>
            <CardHeader><CardTitle>Найпоширеніші професійні дії в добірці</CardTitle>
              <CardDescription>Порядок за поширеністю в добірці. Це вибірка з каталогу, а не дані про ринок праці.</CardDescription></CardHeader>
            <CardContent>
              <ol className="flex flex-col gap-2">
                {visibleMarket?.map((s) => (
                  <li key={s.action_id} className="flex items-center gap-3 rounded-xl border border-line p-3 text-sm">
                    <span className="flex size-7 items-center justify-center rounded-md bg-primary-soft font-semibold text-primary">{s.order}</span>
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
            <CardHeader><CardTitle>Поточний профіль</CardTitle>
              <CardDescription>Оцінки можна лише переглядати. Вони описують ваші відповіді, а не перевірений досвід.</CardDescription></CardHeader>
            <CardContent>
              {scored.length === 0 ? (
                <p className="text-sm text-ink-muted">Оцінок ще немає: автоматична оцінка не змогла опрацювати відповіді.</p>
              ) : (
                <ul className="grid gap-5 sm:grid-cols-2">
                  {scored.slice(0, 5).map((a) => (
                    <li key={a.action_id} className="rounded-2xl border border-line p-4">
                      <ScoreBar name={a.action_name} score={a.score ?? 0} />
                      <p className="mt-2 text-sm text-ink-muted">{a.reason}</p>
                    </li>
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
    </div>
  );
}
