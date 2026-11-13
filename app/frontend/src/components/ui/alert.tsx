import * as React from 'react';
import { cn } from '@/lib/utils';

export const Alert = ({ className, role = 'status', ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    role={role}
    className={cn('rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900', className)}
    {...props}
  />
);
