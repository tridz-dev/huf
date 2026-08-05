import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const buttonVariants = cva(
  // HUF: no rounded corners, no shadows, font-body
  'inline-flex items-center justify-center whitespace-nowrap rounded text-sm font-body font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        // HUF primary: --ink bg, --signal on hover
        default:
          'bg-ink text-primary-foreground hover:bg-signal',
        display:
          'bg-ink text-primary-foreground hover:bg-signal font-display font-bold text-[13px] uppercase tracking-[.06em]',
        destructive:
          'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline:
          'border border-line bg-panel text-ink hover:bg-paper-deep',
        secondary:
          'bg-paper-deep text-ink hover:bg-line',
        ghost: 'text-ink hover:bg-paper-deep',
        link: 'text-signal-ink underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-control-md px-control py-control',
        sm: 'h-control-sm px-control-sm text-xs',
        lg: 'h-control-lg px-control-lg',
        icon: 'h-control-md w-control-md',
        'icon-sm': 'h-control-sm w-control-sm',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
