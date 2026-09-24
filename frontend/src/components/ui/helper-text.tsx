import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

/**
 * Small caption / hint text that sits under a field, control or section.
 *
 * This is the single source of truth for "help text" styling in HUF. It is a
 * plain presentational primitive with no form-library dependency, so it works
 * anywhere. `FormDescription` and `FormMessage` in `./form` delegate to it and
 * only add react-hook-form wiring (ids, aria, error swapping) on top.
 *
 * Tokens (see `src/index.css` Type scale and `DESIGN.md` section 2):
 * - size: `text-xs` -- the sanctioned 12px small tier (Tailwind's own step;
 *   arbitrary `text-[Npx]` / `text-[0.8rem]` sizes are drift).
 * - color: `text-muted-foreground` -> `--steel`, the secondary-text token for
 *   descriptions and metadata; `text-destructive` for validation errors.
 */
const helperTextVariants = cva('text-xs', {
  variants: {
    tone: {
      muted: 'text-muted-foreground',
      destructive: 'font-medium text-destructive',
    },
  },
  defaultVariants: {
    tone: 'muted',
  },
});

export interface HelperTextProps
  extends React.HTMLAttributes<HTMLParagraphElement>,
    VariantProps<typeof helperTextVariants> {}

const HelperText = React.forwardRef<HTMLParagraphElement, HelperTextProps>(
  ({ className, tone, ...props }, ref) => (
    <p ref={ref} className={cn(helperTextVariants({ tone }), className)} {...props} />
  ),
);
HelperText.displayName = 'HelperText';

export { HelperText, helperTextVariants };
