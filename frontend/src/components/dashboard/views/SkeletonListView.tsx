import { cn } from '@/lib/utils';
import { SkeletonListRow } from './SkeletonListRow';

interface SkeletonListViewProps {
  count?: number;
  showBadge?: boolean;
  showLeadingDot?: boolean;
  className?: string;
}

export function SkeletonListView({
  count = 10,
  showBadge = true,
  showLeadingDot = false,
  className,
}: SkeletonListViewProps) {
  return (
    <div className={cn('space-y-3', className)}>
      {Array.from({ length: count }).map((_, index) => (
        <SkeletonListRow
          key={`skeleton-list-row-${index}`}
          showBadge={showBadge}
          showLeadingDot={showLeadingDot}
        />
      ))}
    </div>
  );
}
