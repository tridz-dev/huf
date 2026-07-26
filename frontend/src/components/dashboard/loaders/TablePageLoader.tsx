import { Skeleton } from '@/components/ui/skeleton';
import { FilterBarSkeleton } from './FilterBarSkeleton';
import { SkeletonTable } from '../views/SkeletonTable';
import { PageListFooter } from '../PageListFooter';

interface TablePageLoaderProps {
  filterCount?: number;
  columns?: number;
  rows?: number;
}

export function TablePageLoader({
  filterCount = 2,
  columns = 6,
  rows = 10,
}: TablePageLoaderProps) {
  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6">
        <Skeleton className="h-5 w-80" />
        <FilterBarSkeleton filterCount={filterCount} />
        <SkeletonTable columns={columns} rows={rows} />
        <PageListFooter
          hasMore
          loading={false}
          onLoadMore={() => undefined}
          disabled
        />
      </div>
    </div>
  );
}
