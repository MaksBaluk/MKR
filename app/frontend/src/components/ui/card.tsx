import * as React from 'react';
import { cn } from '@/lib/utils';

export const Card = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_3px_rgba(15,23,42,0.06)]', className)} {...props} />
);

export const CardHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('flex flex-col gap-1 p-5 pb-2', className)} {...props} />
);

export const CardTitle = ({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h2 className={cn('text-lg font-semibold text-slate-900', className)} {...props} />
);

export const CardContent = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('p-5 pt-2', className)} {...props} />
);
