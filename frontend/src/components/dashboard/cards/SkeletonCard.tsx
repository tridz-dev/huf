import { BaseCard } from './BaseCard';
import { CardHeader, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

interface SkeletonCardProps {
  className?: string;
  metadataRows?: number;
  showBadges?: boolean;
}

export function SkeletonCard({
  className,
  metadataRows = 4,
  showBadges = true,
}: SkeletonCardProps) {
  return (
    <BaseCard className={`flex flex-col ${className || ''}`}>
      <div className="flex flex-col flex-1">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between">
            <div className="flex-1 space-y-2">
              <div className="flex items-center gap-2">
                <Skeleton className="h-3 w-3 rounded-full shrink-0" />
                <Skeleton className="h-6 w-3/4" />
              </div>
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6 min-h-[2.5rem]" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full ml-2" />
          </div>
        </CardHeader>

        <CardContent className="flex flex-col flex-1 pb-3">
          <div className="space-y-2 flex-1">
            {Array.from({ length: metadataRows }).map((_, index) => (
              <div key={`metadata-skeleton-${index}`} className="flex items-center justify-between">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-24" />
              </div>
            ))}
          </div>
          {showBadges && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              <Skeleton className="h-5 w-12 rounded-full" />
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
          )}
          <div className="mt-auto pt-1">
            <div className="flex gap-2">
              <Skeleton className="h-8 w-8 rounded-md" />
              <Skeleton className="h-8 w-8 rounded-md" />
            </div>
          </div>
        </CardContent>
      </div>
    </BaseCard>
  );
}
