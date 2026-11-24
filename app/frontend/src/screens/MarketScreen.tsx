import { lazy, Suspense, useEffect, useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '@/api';
import { LazyMarketChart } from '@/components/LazyMarketChart';
import { ScaleLegend } from '@/components/ScaleLegend';
import { ErrorRetry } from '@/components/ErrorRetry';
import { MarketMatrix } from '@/components/MarketMatrix';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { buildMatrix } from '@/lib/marketMatrix';
import { distributionRows, trackOptions, type DistributionItem } from '@/lib/marketChart';
import type { MarketOverview } from '@/lib/marketOverview';
import { DEFAULT_FILTERS, resultsApiPath } from '@/lib/results';
import { NoResultsState, useSelfRatings } from '@/screens/ResultsScreen';
import type { CandidateProfile, ProfileResults } from '@/types';

const MarketCharts = lazy(() => import('@/components/MarketCharts').then((m) => ({ default: m.MarketCharts })));

// recharts for the distribution lives in its own chunk, like the candidate chart.
const MarketDistributionChart = lazy(() =>
  import('@/components/MarketDistributionChart').then((m) => ({ default: m.MarketDistributionChart })));

type Track = 'python' | 'marketing' | 'design';

type Level = 'junior' | 'middle' | 'senior' | 'lead';
interface Distribution {
  track: Track; seniority: Level | null; vacancies_total: number; seniority_totals: Partial<Record<Level, number>>; items: DistributionItem[];
}
const LEVELS: { value: Level; label: string }[] = [
  { value: 'junior', label: 'Junior' }, { value: 'middle', label: 'Middle' }, { value: 'senior', label: 'Senior' }, { value: 'lead', label: 'Lead' },
];

/**
 * Share of vacancies per track that require each action, for all levels or for one: what a Junior, a Middle or a Senior
 * vacancy asks for. Public catalog data; the matrix below puts the candidate's interview grades on the same skills.
 */
function TrackDistribution({ defaultTrack, competencies }: { defaultTrack: string; competencies: ProfileResults['competencies'] }) {
  const track = trackOptions(defaultTrack)[0].value as Track;
  const [level, setLevel] = useState<Level | ''>('');
  const [totals, setTotals] = useState<Distribution['seniority_totals']>({});
  const [data, setData] = useState<Distribution | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const selectId = useId();

  useEffect(() => {
    let live = true;
    setError(null);
    setData(null);
    api<Distribution>(`/market/distribution?track=${track}${level ? `&seniority=${level}` : ''}`)
      .then((r) => { if (live) { setData(r); setTotals(r.seniority_totals); } })
      .catch((err) => live && setError(err instanceof ApiError ? err.message : 'Не вдалося завантажити розподіл.'));
    return () => {
      live = false;
    };
  }, [track, level, nonce]);

  const rows = data ? distributionRows(data.items) : [];
  const segment = level ? `вакансій рівня ${LEVELS.find((l) => l.value === level)?.label}` : 'вакансій треку';
  const all = Object.values(totals).reduce((a, n) => a + (n ?? 0), 0);
  return (
    <>
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>Розподіл компетентностей по вакансіях</CardTitle>
          <CardDescription>Яка частка вакансій потребує кожну навичку і якого рівня вони її вимагають.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <p className="text-sm text-ink-muted">Трек вашого профілю: <span className="font-medium text-ink">{trackOptions(defaultTrack)[0].label}</span></p>
            <div className="flex flex-col gap-1 sm:w-64">
              <label htmlFor={selectId} className="text-sm font-medium text-ink">Рівень вакансій</label>
              <Select id={selectId} value={level} onChange={(e) => setLevel(e.target.value as Level | '')}>
                <option value="">Усі рівні{all ? ` (${all})` : ''}</option>
                {LEVELS.map((l) => (
                  <option key={l.value} value={l.value} disabled={(totals[l.value] ?? 0) === 0 && level !== l.value}>
                    {l.label}{totals[l.value] !== undefined ? ` (${totals[l.value]})` : ''}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          {error ? (
            <ErrorRetry message={error} onRetry={() => setNonce((n) => n + 1)} />
          ) : !data ? (
            <Skeleton className="h-64" />
          ) : data.items.length === 0 ? (
            <p className="text-sm text-ink-muted">Для цього рівня ще немає активних вакансій.</p>
          ) : (
            <Suspense fallback={<Skeleton className="h-64" />}>
              <MarketDistributionChart rows={rows} caption={`Частка вакансій у добірці: ${data.vacancies_total} ${segment}`} />
            </Suspense>
          )}
        </CardContent>
      </Card>
      {data && rows.length > 0 && (
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Матриця «ринок × ваші відповіді»</CardTitle>
            <CardDescription>
              Для кожної навички з переліку вище: скільки {segment} її потребують і наскільки високо оцінили ваші відповіді.
              Змініть рівень вакансій угорі, щоб побачити, де ви сильні для іншого рівня.
            </CardDescription>
          </CardHeader>
          <CardContent><MarketMatrix matrix={buildMatrix(rows, competencies)} /></CardContent>
        </Card>
      )}
    </>
  );
}

/** Extra charts for the candidate's track: levels, work mode, salary, requirement kinds, radar against the market. */
function TrackOverview({ track, competencies }: { track: string; competencies: ProfileResults['competencies'] }) {
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    api<MarketOverview>(`/market/overview?track=${encodeURIComponent(track)}`)
      .then((r) => live && setOverview(r))
      .catch((err) => live && setError(err instanceof ApiError ? err.message : 'Не вдалося завантажити дані ринку.'));
    return () => {
      live = false;
    };
  }, [track, nonce]);
  if (error) return <ErrorRetry message={error} onRetry={() => setNonce((n) => n + 1)} />;
  if (!overview) return <Skeleton className="h-72" />;
  if (overview.vacancies_total === 0) return <p className="text-sm text-ink-muted">Для цього напряму немає даних ринку.</p>;
  return (
    <Suspense fallback={<Skeleton className="h-72" />}>
      <MarketCharts overview={overview} competencies={competencies} />
    </Suspense>
  );
}

/** «Профіль ринку»: market skills in order with the candidate's level, and the per-track distribution. */
export function MarketScreen({ profile }: { profile: CandidateProfile }) {
  const [data, setData] = useState<ProfileResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const self = useSelfRatings(profile.id);

  useEffect(() => {
    let live = true;
    setError(null);
    api<ProfileResults>(resultsApiPath(profile.id, DEFAULT_FILTERS, 1))
      .then((r) => live && setData(r))
      .catch((err) => live && setError(err instanceof ApiError ? err.message : 'Не вдалося завантажити дані.'));
    return () => {
      live = false;
    };
  }, [profile.id, nonce]);

  if (error)
    return (
      <ErrorRetry message={error} onRetry={() => setNonce((n) => n + 1)} />
    );
  if (!data)
    return (
      <div aria-busy="true">
        <p role="status" className="sr-only">Завантаження…</p>
        <Skeleton className="h-96" />
      </div>
    );
  if (!data.has_results) return <NoResultsState profile={profile} />;
  return (
    <div className="flex flex-col gap-6">
      <TrackDistribution defaultTrack={profile.track ?? ''} competencies={data.competencies} />
      <TrackOverview track={trackOptions(profile.track ?? '')[0].value} competencies={data.competencies} />
      <div>
        <h2 className="mb-3 text-lg font-semibold text-ink">Ваш рівень проти вимог добірки</h2>
        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <Card className="min-w-0">
        <CardContent className="pt-5 sm:pt-6">
          <LazyMarketChart market={data.market} competencies={data.competencies} selfRatings={self.items ?? []} />
        </CardContent>
      </Card>
      <div className="flex flex-col gap-4">
        <ScaleLegend className="bg-surface" />
        <p className="text-xs text-ink-subtle">
          Перелік побудовано за вакансіями вашої добірки, а не за даними всього ринку праці.{' '}
          <Link to="/results" className="underline underline-offset-2 hover:text-ink">До результатів</Link>
        </p>
      </div>
        </div>
      </div>
    </div>
  );
}
