import { Badge } from '@/components/ui/badge';
import { bandFor } from '@/lib/bands';

export function ScoreBar({ name, score }: { name: string; score: number }) {
  const band = bandFor(score);
  return (
    <li className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-slate-900">{name}</span>
        <span className="text-sm font-semibold tabular-nums text-slate-700">{score.toFixed(2)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${name}: ${band.label}, ${score.toFixed(2)}`}>
        <div
          className={`h-full rounded-full ${band.bar} transition-[width] duration-700 motion-reduce:transition-none`}
          style={{ width: `${Math.round(score * 100)}%` }}
        />
      </div>
      <Badge variant={band.badge} className="self-end">{band.label}</Badge>
    </li>
  );
}
