import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const badgeVariants = cva(
  // HUF: three chip families — mono/uppercase machine-id pills (default/secondary/destructive/success/outline),
  // filled sentence-case status pills (pill-*) for agent/run/tool status,
  // and compact model-name chips (chip) with 6px radius and normal-case text.
  'inline-flex items-center border px-2 py-0.5 text-[10.5px] transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  {
    variants: {
      variant: {
        default:
          'rounded-full border-line bg-paper-deep text-steel font-mono uppercase tracking-wide',
        secondary:
          'rounded-full border-line bg-paper-deep text-steel font-mono uppercase tracking-wide',
        destructive:
          'rounded-full border-signal-ink/40 bg-transparent text-signal-ink font-mono uppercase tracking-wide',
        success:
          'rounded-full border-good/40 bg-transparent text-good font-mono uppercase tracking-wide',
        outline: 'rounded-full border-line text-steel font-mono uppercase tracking-wide',
        'pill-success': 'rounded-full border-transparent bg-[#e8f5ee] text-good font-sans normal-case tracking-normal text-[11px] font-medium',
        'pill-warning': 'rounded-full border-transparent bg-warning-tint text-warning font-sans normal-case tracking-normal text-[11px] font-medium',
        'pill-danger': 'rounded-full border-transparent bg-destructive-tint text-destructive font-sans normal-case tracking-normal text-[11px] font-medium',
        'pill-neutral': 'rounded-full border-transparent bg-paper-deep text-steel font-sans normal-case tracking-normal text-[11px] font-medium',
        chip: 'rounded-sm border-transparent bg-paper-deep text-steel font-mono normal-case tracking-normal',
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
