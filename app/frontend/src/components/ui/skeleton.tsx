import { cn } from '@/lib/utils';

export const Skeleton = ({ className }: { className?: string }) => (
  <div aria-hidden="true" className={cn('animate-pulse rounded-xl bg-surface-muted motion-reduce:animate-none', className)} />
);
