import { cn } from '@/lib/utils';

export const Progress = ({ value, label, className }: { value: number; label: string; className?: string }) => (
  <div
    role="progressbar"
    aria-label={label}
    aria-valuemin={0}
    aria-valuemax={100}
    aria-valuenow={Math.round(value)}
    className={cn('h-2 w-full overflow-hidden rounded-full bg-slate-200', className)}
  >
    <div
      className="h-full bg-blue-600 transition-[width] duration-300 motion-reduce:transition-none"
      style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
    />
  </div>
);
