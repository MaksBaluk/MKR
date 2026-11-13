import { lazy, Suspense, type ComponentProps } from 'react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import type { MarketChart as MarketChartType } from '@/components/MarketChart';

// recharts lives in its own chunk: only routes that show the chart download it.
const MarketChart = lazy(() => import('@/components/MarketChart').then((m) => ({ default: m.MarketChart })));

/** Code-split MarketChart with a placeholder of roughly the chart's height while the chunk loads. */
export function LazyMarketChart(props: ComponentProps<typeof MarketChartType>) {
  const rows = Math.min(props.market.length, 10);
  return (
    <ErrorBoundary>
      <Suspense fallback={
        <div aria-busy="true" className="flex" style={{ height: rows * 40 + 160 }}>
          <p role="status" className="sr-only">Завантаження діаграми…</p>
          <Skeleton className="w-full" />
        </div>
      }>
        <MarketChart {...props} />
      </Suspense>
    </ErrorBoundary>
  );
}
