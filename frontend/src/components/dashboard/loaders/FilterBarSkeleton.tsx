import { Fragment } from 'react';
import { Skeleton } from '@/components/ui/skeleton';

interface FilterBarSkeletonProps {
  filterCount?: number;
}

export function FilterBarSkeleton({ filterCount = 2 }: FilterBarSkeletonProps) {
  return (
    <div className="flex items-stretch rounded border border-ink bg-panel">
      <div className="flex flex-1 items-center gap-2 px-3.5 py-3">
        <Skeleton className="h-4 w-4 rounded-full" />
        <Skeleton className="h-3.5 w-40" />
      </div>
      {Array.from({ length: filterCount }).map((_, index) => (
        <Fragment key={`filter-skeleton-${index}`}>
          <div className="w-px self-stretch bg-line" />
          <div className="flex min-w-[150px] items-center px-4">
            <Skeleton className="h-3 w-24" />
          </div>
        </Fragment>
      ))}
    </div>
  );
}
