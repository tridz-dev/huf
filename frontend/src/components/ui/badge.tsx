import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const badgeVariants = cva(
  // HUF: two chip families — mono/uppercase machine-id chips (default/secondary/destructive/success/outline),
  // and filled sentence-case status pills (pill-*) for agent/run/tool status.
  'inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  {
    variants: {
      variant: {
        default:
          'border-line bg-paper-deep text-steel font-mono uppercase tracking-wide',
        secondary:
          'border-line bg-paper-deep text-steel font-mono uppercase tracking-wide',
        destructive:
          'border-signal-ink/40 bg-transparent text-signal-ink font-mono uppercase tracking-wide',
        success:
          'border-good/40 bg-transparent text-good font-mono uppercase tracking-wide',
        outline: 'border-line text-steel font-mono uppercase tracking-wide',
        'pill-success': 'border-transparent bg-[#e8f5ee] text-good font-sans normal-case tracking-normal text-[11px] font-medium',
        'pill-warning': 'border-transparent bg-[#fdf3e0] text-[#8a5a00] font-sans normal-case tracking-normal text-[11px] font-medium',
        'pill-danger': 'border-transparent bg-destructive-tint text-destructive font-sans normal-case tracking-normal text-[11px] font-medium',
        'pill-neutral': 'border-transparent bg-paper-deep text-steel font-sans normal-case tracking-normal text-[11px] font-medium',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
