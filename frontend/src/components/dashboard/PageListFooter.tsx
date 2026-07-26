import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface PageListFooterProps {
  hasMore: boolean;
  loading: boolean;
  onLoadMore: () => void;
  disabled?: boolean;
  endMessage?: string;
  loadMoreLabel?: string;
  className?: string;
}

export function PageListFooter({
  hasMore,
  loading,
  onLoadMore,
  disabled = false,
  endMessage,
  loadMoreLabel = 'Load More',
  className,
}: PageListFooterProps) {
  const showLoadMore = hasMore && !disabled;
  const showEndMessage = !hasMore && Boolean(endMessage);

  return (
    <div
      className={cn(
        'flex min-h-[88px] flex-col items-center justify-center py-8',
        className,
      )}
    >
      {showLoadMore ? (
        <Button onClick={onLoadMore} disabled={loading} variant="outline">
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Loading...
            </>
          ) : (
            loadMoreLabel
          )}
        </Button>
      ) : showEndMessage ? (
        <p className="text-sm text-muted-foreground">{endMessage}</p>
      ) : null}
    </div>
  );
}
