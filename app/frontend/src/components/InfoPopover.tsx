import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Info } from 'lucide-react';

/** Small disclosure popover behind an info button: click/Enter toggles, Esc and outside click close. */
export function InfoPopover({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <span ref={root} className="relative inline-flex">
      <button ref={button} type="button" aria-label={label} aria-expanded={open} aria-controls={id}
        onClick={() => setOpen(!open)}
        className="inline-flex size-8 cursor-pointer items-center justify-center rounded-full text-ink-subtle hover:bg-surface-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        <Info className="size-4" aria-hidden="true" />
      </button>
      {open && (
        <span id={id} role="note"
          className="absolute top-full right-0 z-20 mt-1 w-64 max-w-[calc(100vw-2rem)] rounded-xl border border-line bg-surface p-3 text-xs leading-relaxed text-ink-muted shadow-raised">
          {children}
        </span>
      )}
    </span>
  );
}
