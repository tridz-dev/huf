import * as React from 'react';

import { cn } from '@/lib/utils';

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          'flex min-h-[calc(var(--control-h-md)*2)] w-full rounded border border-input bg-transparent px-control py-control-y text-ui-text placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-signal focus-visible:ring-[3px] focus-visible:ring-signal/[.14] disabled:cursor-not-allowed disabled:opacity-50',
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Textarea.displayName = 'Textarea';

export { Textarea };
