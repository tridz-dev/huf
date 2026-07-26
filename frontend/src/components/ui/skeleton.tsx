import { cn } from '@/lib/utils';

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-none bg-paper-deep', className)}
      {...props}
    />
  );
}

export { Skeleton };
