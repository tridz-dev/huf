import { Skeleton } from '@/components/ui/skeleton';
import { FilterBarSkeleton } from './FilterBarSkeleton';
import { SkeletonGridView } from '../views/SkeletonGridView';
import { PageListFooter } from '../PageListFooter';

interface GridPageLoaderProps {
  filterCount?: number;
  skeletonCount?: number;
}

export function GridPageLoader({
  filterCount = 2,
  skeletonCount = 20,
}: GridPageLoaderProps) {
  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6">
        <Skeleton className="h-5 w-80" />
        <FilterBarSkeleton filterCount={filterCount} />
        <SkeletonGridView count={skeletonCount} />
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
