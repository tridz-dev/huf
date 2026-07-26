import * as React from 'react';

import { cn } from '@/lib/utils';
import { DialogContent, DialogFooter, DialogHeader } from '@/components/ui/dialog';

export function DialogScrollContent({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogContent>) {
  return (
    <DialogContent
      className={cn(
        'flex max-h-[min(85vh,100dvh)] flex-col overflow-hidden p-0 sm:max-h-[min(85vh,100dvh)]',
        className,
      )}
      {...props}
    />
  );
}

export function DialogScrollHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <DialogHeader className={cn('flex-shrink-0 px-6 pt-6', className)} {...props} />;
}

export function DialogScrollBody({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('min-h-0 flex-1 overflow-y-auto px-6', className)} {...props} />;
}

export function DialogScrollFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <DialogFooter
      className={cn('flex-shrink-0 flex-wrap gap-2 border-t px-6 py-4', className)}
      {...props}
    />
  );
}
