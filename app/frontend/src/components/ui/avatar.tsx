import { initials } from '@/lib/bands';
import { cn } from '@/lib/utils';

/** Initials avatar. Decorative: the name is always rendered as text next to it. */
export function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'flex size-10 shrink-0 select-none items-center justify-center rounded-full bg-gradient-to-br from-primary to-brand-deep text-sm font-semibold text-on-primary',
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
