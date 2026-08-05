import * as React from 'react';
import * as LabelPrimitive from '@radix-ui/react-label';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const labelVariants = cva(
  'font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70',
  {
    variants: {
      // A parity audit found 78 callsite overrides on Label, 43 of them the
      // single class `text-xs` — that is a missing size, not 43 mistakes.
      // `sm` is the dense-panel/inspector label; `eyebrow` is the mono
      // uppercase group label the design system already defines.
      size: {
        default: 'text-sm',
        sm: 'text-xs',
        eyebrow: 'font-mono text-eyebrow uppercase text-steel-soft',
      },
    },
    defaultVariants: { size: 'default' },
  },
);

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> &
    VariantProps<typeof labelVariants>
>(({ className, size, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(labelVariants({ size }), className)}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
