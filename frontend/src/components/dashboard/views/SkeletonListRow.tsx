import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface SkeletonListRowProps {
  showBadge?: boolean;
  showLeadingDot?: boolean;
  className?: string;
}

export function SkeletonListRow({
  showBadge = true,
  showLeadingDot = false,
  className,
}: SkeletonListRowProps) {
  return (
    <div
      className={cn(
        'flex items-center justify-between p-3 rounded-lg border',
        className,
      )}
    >
      <div className="flex items-center gap-3 flex-1 min-w-0">
        {showLeadingDot && (
          <Skeleton className="w-2.5 h-2.5 rounded-full shrink-0" />
        )}
        <div className="flex-1 min-w-0 space-y-2">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-3 w-3/5" />
        </div>
      </div>
      {showBadge && <Skeleton className="h-5 w-16 rounded-full shrink-0 ml-3" />}
    </div>
  );
}
