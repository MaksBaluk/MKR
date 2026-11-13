import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

const alertVariants = cva('flex items-start gap-2.5 rounded-xl border p-3 text-sm', {
  variants: {
    variant: {
      warning: 'border-warning/30 bg-warning-soft text-warning-ink',
      danger: 'border-danger/30 bg-danger-soft text-danger-ink',
      info: 'border-primary-line bg-info-soft text-info-ink',
      success: 'border-success/30 bg-success-soft text-success-ink',
    },
  },
  defaultVariants: { variant: 'warning' },
});

const ICONS = { warning: AlertTriangle, danger: XCircle, info: Info, success: CheckCircle2 } as const;

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof alertVariants> {
  /** Set false when the children already start with their own icon. */
  icon?: boolean;
}

/** Status message. Icon + text, never colour alone. `role="alert"` for errors, `status` otherwise. */
export const Alert = ({ className, role = 'status', variant, icon = true, children, ...props }: AlertProps) => {
  const Icon = ICONS[variant ?? 'warning'];
  return (
    <div role={role} className={cn(alertVariants({ variant }), className)} {...props}>
      {icon && <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
};
