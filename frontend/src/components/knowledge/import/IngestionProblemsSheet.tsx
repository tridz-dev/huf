import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import {
  getIngestionStatus,
  retryIngestion,
  type IngestionItem,
  type IngestionStatusResult,
} from '@/services/knowledgeApi';
import { itemReason, itemStatusLabel } from './ingestionLabels';

type Filter = 'all' | 'Error' | 'Skipped';
const PAGE = 50;

interface IngestionProblemsSheetProps {
  ingestion: string | null;
  onOpenChange: (open: boolean) => void;
  onRetried?: () => void;
}

export function IngestionProblemsSheet({ ingestion, onOpenChange, onRetried }: IngestionProblemsSheetProps) {
  const [filter, setFilter] = useState<Filter>('all');
  const [items, setItems] = useState<IngestionItem[]>([]);
  const [summary, setSummary] = useState<IngestionStatusResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [page, setPage] = useState(0);

  const load = useCallback(
    async (pageIndex: number, replace: boolean) => {
      if (!ingestion) return;
      const start = pageIndex * PAGE;
      setLoading(true);
      try {
        // "All" in the problems list means failed and skipped, never the happy path.
        const statuses = filter === 'all' ? ['Error', 'Skipped'] : [filter];
        const results = await Promise.all(
          statuses.map((s) =>
            getIngestionStatus(ingestion, { includeItems: true, itemStatus: s, limit: PAGE, start }),
          ),
        );
        const merged = results.flatMap((r) => r.items);
        setSummary(results[0]);
        setHasMore(results.some((r) => r.items.length === PAGE));
        setItems((prev) => (replace ? merged : [...prev, ...merged]));
        setPage(pageIndex);
      } catch (e) {
        toast.error(getFrappeErrorMessage(e) || 'Could not load the file list');
      } finally {
        setLoading(false);
      }
    },
    [ingestion, filter],
  );

  useEffect(() => {
    if (ingestion) void load(0, true);
  }, [ingestion, filter, load]);

  const failedCount = summary?.counts.error ?? 0;
  const skippedCount = summary?.counts.skipped ?? 0;

  const retry = async () => {
    if (!ingestion) return;
    setRetrying(true);
    try {
      await retryIngestion(ingestion, true);
      toast.success(`Retrying ${failedCount} ${failedCount === 1 ? 'file' : 'files'}`);
      onOpenChange(false);
      onRetried?.();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e) || 'Could not retry');
    } finally {
      setRetrying(false);
    }
  };

  return (
    <Sheet open={!!ingestion} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-auto sm:max-w-xl" data-testid="problems-sheet">
        <SheetHeader>
          <SheetTitle>Files that need a look</SheetTitle>
          <SheetDescription>
            {failedCount} failed, {skippedCount} skipped. Skipped files are not an error: we could not use them.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {(['all', 'Error', 'Skipped'] as Filter[]).map((f) => (
            <Button
              key={f}
              type="button"
              size="sm"
              variant={filter === f ? 'default' : 'outline'}
              onClick={() => setFilter(f)}
            >
              {f === 'all' ? 'All' : f === 'Error' ? 'Failed' : 'Skipped'}
            </Button>
          ))}
          <div className="ml-auto">
            <Button
              type="button"
              size="sm"
              disabled={failedCount === 0 || retrying}
              onClick={() => void retry()}
              data-testid="retry-failed"
            >
              {retrying && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Retry failed ({failedCount})
            </Button>
          </div>
        </div>
        <ul className="mt-4 space-y-2">
          {items.map((item) => (
            <li key={item.name} className="rounded-md border p-3" data-testid="problem-item">
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 break-words text-sm font-medium">{item.file_name || item.external_key || item.name}</p>
                <Badge variant={item.status === 'Error' ? 'pill-danger' : 'pill-neutral'}>
                  {itemStatusLabel(item.status)}
                </Badge>
              </div>
              <p className="mt-1 text-sm text-steel">{itemReason(item)}</p>
              {item.status === 'Error' && item.error_message && (
                <Collapsible>
                  <CollapsibleTrigger className="mt-1 text-xs text-signal-ink underline">
                    Technical details
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-1 whitespace-pre-wrap break-words text-xs text-steel-soft">
                    {item.error_message}
                  </CollapsibleContent>
                </Collapsible>
              )}
            </li>
          ))}
        </ul>
        {loading && (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-steel-soft" />
          </div>
        )}
        {!loading && items.length === 0 && (
          <p className="py-6 text-center text-sm text-steel">Nothing to show here.</p>
        )}
        {!loading && hasMore && (
          <div className="mt-3 flex justify-center">
            <Button type="button" variant="outline" size="sm" onClick={() => void load(page + 1, false)}>
              Show more
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
