import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface LoadMoreButtonProps {
  hasMore: boolean;
  loading: boolean;
  onLoadMore: () => void;
  disabled?: boolean;
}

export function LoadMoreButton({
  hasMore,
  loading,
  onLoadMore,
  disabled = false,
}: LoadMoreButtonProps) {
  if (!hasMore || disabled) {
    return null;
  }

  return (
    <div className="flex justify-center py-8">
      <Button
        onClick={onLoadMore}
        disabled={loading}
        variant="outline"
      >
        {loading ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Loading...
          </>
        ) : (
          'Load More'
        )}
      </Button>
    </div>
  );
}

