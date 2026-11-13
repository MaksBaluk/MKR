import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export function EmptyState({ icon: Icon, title, children, action, className, headingLevel = 2 }: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
  headingLevel?: 2 | 3;
}) {
  const Heading = headingLevel === 2 ? 'h2' : 'h3';
  return (
    <Card className={cn('flex flex-col items-center gap-3 px-6 py-10 text-center sm:py-14', className)}>
      <span className="flex size-14 items-center justify-center rounded-2xl bg-primary-soft text-primary">
        <Icon className="size-7" aria-hidden="true" />
      </span>
      <Heading className="text-lg font-semibold tracking-tight text-ink">{title}</Heading>
      {children && <div className="max-w-md text-sm text-ink-muted">{children}</div>}
      {action && <div className="mt-2 flex flex-wrap justify-center gap-2">{action}</div>}
    </Card>
  );
}
