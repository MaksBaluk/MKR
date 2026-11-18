import { Building2 } from 'lucide-react';

const TILE: Record<string, { letter: string; cls: string }> = {
  Djinni: { letter: 'd', cls: 'bg-ink text-surface' },
  'robota.ua': { letter: 'r', cls: 'bg-primary text-surface' },
  'work.ua': { letter: 'w', cls: 'bg-success text-surface' },
  DOU: { letter: 'D', cls: 'bg-warning text-ink' },
};

export const EXAMPLE_NOTE = 'Адаптований приклад вакансії, не оригінальне оголошення.';

/** Provenance tile from the API `source_label`; an example vacancy says so in its tooltip and screen-reader text. */
export function SourceMark({ label, example = false }: { label: string | null; example?: boolean }) {
  const base = 'flex size-12 shrink-0 items-center justify-center rounded-xl';
  const tile = label ? TILE[label] : undefined;
  const text = label ? (example ? `Джерело: ${label}. ${EXAMPLE_NOTE}` : `Джерело: ${label}`) : undefined;
  if (tile)
    return (
      <span className={`${base} ${tile.cls} text-2xl font-bold leading-none`} title={text}>
        <span aria-hidden="true">{tile.letter}</span>
        <span className="sr-only">{text}</span>
      </span>
    );
  return (
    <span className={`${base} border border-line bg-canvas text-ink-subtle`} title={text}>
      <Building2 className="size-6" aria-hidden="true" />
      {text && <span className="sr-only">{text}</span>}
    </span>
  );
}
