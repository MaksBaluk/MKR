import { useEffect, useId, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Native <dialog> as a modal: the browser provides the focus trap, Esc to close and inert background.
 * `side="left"` renders a full-height drawer (mobile navigation).
 */
export function Dialog({ open, onClose, title, children, side, className }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  side?: 'left';
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    else if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog ref={ref} aria-labelledby={titleId} onClose={onClose}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      className={cn(
        'bg-surface text-ink shadow-raised backdrop:bg-ink/40 backdrop:backdrop-blur-[2px]',
        side === 'left'
          ? 'fixed inset-y-0 left-0 m-0 h-dvh max-h-none w-[min(20rem,85vw)] max-w-none rounded-r-2xl'
          : 'm-auto w-[min(36rem,calc(100vw-2rem))] rounded-2xl',
        className,
      )}>
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
        <h2 id={titleId} className="text-base font-semibold text-ink">{title}</h2>
        <button type="button" onClick={onClose} aria-label="Закрити"
          className="-mr-2 flex size-11 cursor-pointer items-center justify-center rounded-xl text-ink-subtle hover:bg-surface-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-ring">
          <X className="size-5" aria-hidden="true" />
        </button>
      </div>
      <div className="p-5">{children}</div>
    </dialog>
  );
}
