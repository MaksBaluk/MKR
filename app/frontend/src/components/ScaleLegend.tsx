import { cn } from '@/lib/utils';

/** The assessment scale in words. Numbers like 0.75 never appear without this explanation. */
export const SCALE_LEVELS = [
  { label: 'Високий', swatch: 'bg-success', text: 'відповіді показали впевнене володіння з конкретними прикладами, рішеннями та їхніми наслідками.' },
  { label: 'Середній', swatch: 'bg-primary', text: 'відповіді показали робоче розуміння, але прикладів або глибини поки небагато.' },
  { label: 'Низький', swatch: 'bg-warning', text: 'відповіді були загальними або містили неточності.' },
  { label: 'Немає оцінки', swatch: 'bg-hatch', text: 'у відповідях недостатньо свідчень, щоб оцінити цю дію.' },
] as const;

export function ScaleLegend({ className }: { className?: string }) {
  return (
    <div className={cn('rounded-xl border border-line bg-canvas p-4 text-sm', className)}>
      <h3 className="font-semibold text-ink">Як читати рівні</h3>
      <ul className="mt-2 flex flex-col gap-1.5">
        {SCALE_LEVELS.map((l) => (
          <li key={l.label} className="flex gap-2">
            <span aria-hidden="true" className={cn('mt-1 size-3 shrink-0 rounded-sm border border-line-strong', l.swatch)} />
            <span className="text-ink-muted"><span className="font-semibold text-ink">{l.label}</span> — {l.text}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-ink-subtle">
        Рівні описують відповіді, які ви дали в співбесіді, а не перевірений досвід роботи.
      </p>
    </div>
  );
}
