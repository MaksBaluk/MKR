import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex max-w-full cursor-pointer items-center justify-center gap-2 rounded-xl text-center text-sm font-semibold transition-[background-color,border-color,color,box-shadow] duration-150 motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-on-primary shadow-sm hover:bg-primary-hover',
        outline: 'border border-line-strong bg-surface text-ink hover:border-primary-line hover:bg-primary-soft',
        secondary: 'bg-primary-soft text-primary-strong hover:bg-primary-line/60',
        ghost: 'text-ink-muted hover:bg-surface-muted hover:text-ink',
      },
      // Every size keeps a 44px hit area on touch screens (WCAG 2.5.5 / Apple HIG).
      size: {
        default: 'min-h-11 px-4 py-2',
        sm: 'min-h-11 px-3 py-1.5 sm:min-h-9',
        lg: 'min-h-12 px-6 py-2.5 text-base',
        icon: 'size-11 shrink-0',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
  },
);
Button.displayName = 'Button';
