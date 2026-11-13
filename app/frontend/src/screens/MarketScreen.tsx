import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '@/api';
import { MarketChart } from '@/components/MarketChart';
import { ScaleLegend } from '@/components/ScaleLegend';
import { ErrorRetry } from '@/components/ErrorRetry';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { DEFAULT_FILTERS, resultsApiPath } from '@/lib/results';
import { NoResultsState, useSelfRatings } from '@/screens/ResultsScreen';
import type { CandidateProfile, ProfileResults } from '@/types';

/** «Профіль ринку»: the cohort's market skills in order with the candidate's level. No market numbers. */
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
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <Card>
        <CardContent className="pt-5 sm:pt-6">
          <MarketChart market={data.market} competencies={data.competencies} selfRatings={self.items ?? []} />
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
  );
}
