import * as React from 'react';

import { cn } from '@/lib/utils';

// `size` is omitted from the inherited attributes because <input> already
// declares an HTML `size` attribute typed as number; a string union would
// collide with it. Same reason SelectTrigger omits it.
export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  /**
   * `sm` is the dense data-table / inspector field, matching SelectTrigger's
   * `sm` so a row of mixed controls lines up.
   */
  size?: 'default' | 'sm';
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, size = 'default', ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          'flex w-full rounded border border-input bg-transparent transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-signal focus-visible:ring-[3px] focus-visible:ring-signal/[.14] disabled:cursor-not-allowed disabled:opacity-50',
          size === 'sm'
            ? 'h-control-sm px-control-sm py-0 text-micro'
            : 'h-control-md px-control py-control-y text-ui-text',
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = 'Input';

export { Input };
