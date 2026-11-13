import { useRef, type KeyboardEvent } from 'react';
import { cn } from '@/lib/utils';

export interface TabItem<T extends string> {
  id: T;
  label: string;
}

/** WAI-ARIA tabs with roving tabindex: arrows / Home / End move and activate. Panels use `panel-${id}`. */
export function Tabs<T extends string>({ items, value, onChange, label, className }: {
  items: readonly TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  label: string;
  className?: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const i = items.findIndex((t) => t.id === value);
    const next =
      e.key === 'ArrowRight' ? (i + 1) % items.length
      : e.key === 'ArrowLeft' ? (i - 1 + items.length) % items.length
      : e.key === 'Home' ? 0
      : e.key === 'End' ? items.length - 1
      : -1;
    if (next < 0) return;
    e.preventDefault();
    onChange(items[next].id);
    refs.current[items[next].id]?.focus();
  }

  return (
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown}
      className={cn('flex max-w-full gap-1 overflow-x-auto rounded-2xl [scrollbar-width:none] border border-line bg-surface p-1 shadow-card', className)}>
      {items.map((t) => {
        const selected = t.id === value;
        return (
          <button key={t.id} ref={(el) => { refs.current[t.id] = el; }} type="button" role="tab" id={`tab-${t.id}`}
            aria-selected={selected} aria-controls={`panel-${t.id}`} tabIndex={selected ? 0 : -1}
            onClick={() => onChange(t.id)}
            className={cn(
              'min-h-11 shrink-0 cursor-pointer rounded-xl px-4 text-sm font-medium whitespace-nowrap transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
              selected ? 'bg-primary text-on-primary shadow-sm' : 'text-ink-muted hover:bg-surface-muted hover:text-ink',
            )}>
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
