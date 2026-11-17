import { Building2 } from 'lucide-react';

/** Provenance tile from the API `source_label`: a dark «d» tile for Djinni, a neutral tile otherwise. */
export function SourceMark({ label }: { label: string | null }) {
  const base = 'flex size-12 shrink-0 items-center justify-center rounded-xl';
  if (label === 'Djinni')
    return (
      <span className={`${base} bg-ink text-2xl font-bold leading-none text-surface`} title="Джерело: Djinni">
        <span aria-hidden="true">d</span>
        <span className="sr-only">Джерело: Djinni</span>
      </span>
    );
  return (
    <span className={`${base} border border-line bg-canvas text-ink-subtle`}>
      <Building2 className="size-6" aria-hidden="true" />
    </span>
  );
}
