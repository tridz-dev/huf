import { Skeleton } from '@/components/ui/skeleton';

interface FilterBarSkeletonProps {
  filterCount?: number;
}

export function FilterBarSkeleton({ filterCount = 2 }: FilterBarSkeletonProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <Skeleton className="h-9 w-full sm:max-w-xs" />
      <div className="flex flex-wrap items-center gap-2">
        {Array.from({ length: filterCount }).map((_, index) => (
          <Skeleton key={`filter-skeleton-${index}`} className="h-9 w-[140px]" />
        ))}
      </div>
    </div>
  );
}
