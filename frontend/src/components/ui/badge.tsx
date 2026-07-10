import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const badgeVariants = cva(
  // HUF: no pill, no fill, mono label — border + text only
  'inline-flex items-center rounded-none border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  {
    variants: {
      variant: {
        default:
          'border-line bg-paper-deep text-steel',
        secondary:
          'border-line bg-paper-deep text-steel',
        destructive:
          'border-destructive/30 bg-transparent text-destructive',
        outline: 'border-line text-steel',
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
