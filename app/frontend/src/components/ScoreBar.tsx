import { Badge } from '@/components/ui/badge';
import { bandFor } from '@/lib/bands';

/** Score row: name, numeric value, bar and a text band (meaning never relies on colour alone). Wrap in `<li>` inside lists. */
export function ScoreBar({ name, score }: { name: string; score: number }) {
  const band = bandFor(score);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-ink">{name}</span>
        <span className="text-sm font-semibold tabular-nums text-ink-muted">{score.toFixed(2)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-muted" role="img" aria-label={`${name}: ${band.label}, ${score.toFixed(2)}`}>
        <div
          className={`h-full rounded-full ${band.bar} transition-[width] duration-700 motion-reduce:transition-none`}
          style={{ width: `${Math.round(score * 100)}%` }}
        />
      </div>
      <Badge variant={band.badge} className="self-end">{band.label}</Badge>
    </div>
  );
}
