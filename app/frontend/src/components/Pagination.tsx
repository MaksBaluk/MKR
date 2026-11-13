import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { pageRange } from '@/lib/results';

/** Page buttons with previous/next; renders nothing for a single page. */
export function Pagination({ page, pages, onPage, label = 'Сторінки результатів' }: {
  page: number;
  pages: number;
  onPage: (p: number) => void;
  label?: string;
}) {
  if (pages <= 1) return null;
  return (
    <nav aria-label={label} className="flex flex-wrap items-center justify-center gap-1.5">
      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        <ChevronLeft className="size-4" aria-hidden="true" />Попередня
      </Button>
      <ul className="flex flex-wrap items-center gap-1">
        {pageRange(page, pages).map((p, i) =>
          p === 'gap' ? (
            <li key={`gap-${i}`} aria-hidden="true" className="px-1 text-ink-subtle">…</li>
          ) : (
            <li key={p}>
              <Button variant={p === page ? 'default' : 'ghost'} size="sm" className="min-w-11 tabular-nums"
                aria-current={p === page ? 'page' : undefined} aria-label={`Сторінка ${p}`} onClick={() => onPage(p)}>
                {p}
              </Button>
            </li>
          ),
        )}
      </ul>
      <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Наступна<ChevronRight className="size-4" aria-hidden="true" />
      </Button>
    </nav>
  );
}
