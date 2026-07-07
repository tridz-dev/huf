import { SkeletonCard } from '../cards/SkeletonCard';
import { getGridClasses, GridViewColumns } from './GridView';
import { cn } from '@/lib/utils';

interface SkeletonGridViewProps {
  columns?: GridViewColumns;
  gap?: number;
  count?: number;
  metadataRows?: number;
  showBadges?: boolean;
  className?: string;
}

export function SkeletonGridView({
  columns = { sm: 1, md: 2, lg: 3 },
  gap = 4,
  count = 20,
  metadataRows = 4,
  showBadges = true,
  className,
}: SkeletonGridViewProps) {
  return (
    <div className={cn(getGridClasses(columns, gap), className)}>
      {Array.from({ length: count }).map((_, index) => (
        <SkeletonCard
          key={`skeleton-${index}`}
          metadataRows={metadataRows}
          showBadges={showBadges}
        />
      ))}
    </div>
  );
}
