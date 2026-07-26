import { SkeletonCard } from '../cards/SkeletonCard';
import { getGridClasses, GridViewColumns } from './GridView';
import { cn } from '@/lib/utils';

interface SkeletonGridViewProps {
  columns?: GridViewColumns;
  gap?: number;
  count?: number;
  className?: string;
}

export function SkeletonGridView({
  columns = { sm: 1, md: 2, lg: 3 },
  gap = 4,
  count = 6,
  className,
}: SkeletonGridViewProps) {
  return (
    <div className={cn(getGridClasses(columns, gap), className)}>
      {Array.from({ length: count }).map((_, index) => (
        <SkeletonCard key={`skeleton-${index}`} />
      ))}
    </div>
  );
}
