import * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * Inline help text styled like `@/components/ui/form`'s `FormDescription`, but usable
 * outside a react-hook-form `<Form>`/`<FormField>` tree.
 *
 * `FormDescription` calls `useFormField()`, which destructures `getFieldState` off
 * `useFormContext()` -- that throws ("Cannot destructure property 'getFieldState' of
 * 'St(...)' as it is null") on any screen that isn't itself a react-hook-form form
 * (the Decision Playground, the Decisions policy list/editor, the setup wizard, ...).
 * Use this component on those screens instead; the two render identically.
 */
export const FieldHelp = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p ref={ref} className={cn('text-[0.8rem] text-muted-foreground', className)} {...props} />
));
FieldHelp.displayName = 'FieldHelp';
