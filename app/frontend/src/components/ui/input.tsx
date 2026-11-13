import * as React from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

const field =
  'w-full rounded-xl border border-line-strong bg-surface px-3.5 text-base text-ink placeholder:text-ink-subtle transition-colors duration-150 motion-reduce:transition-none hover:border-ink-subtle/60 focus-visible:border-primary focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-ring/40 aria-invalid:border-danger aria-invalid:focus-visible:outline-danger/40 disabled:cursor-not-allowed disabled:opacity-50 sm:text-sm';

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(field, 'h-11', className)} {...props} />,
);
Input.displayName = 'Input';

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => <textarea ref={ref} className={cn(field, 'min-h-24 py-2.5', className)} {...props} />,
);
Textarea.displayName = 'Textarea';

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => (
    <div className="relative">
      <select ref={ref} className={cn(field, 'h-11 cursor-pointer appearance-none pr-10', className)} {...props} />
      <ChevronDown className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-subtle" aria-hidden="true" />
    </div>
  ),
);
Select.displayName = 'Select';
