import { Zap, Calendar, Loader2 } from 'lucide-react';
import { FilterBar, GridView, PageLayout, ItemCard } from '@/components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getAgentRuns, type AgentRunDoc } from '@/services/agentRunApi';
import { formatTimeAgo, calculateDuration } from '@/utils/time';
import { Button } from '@/components/ui/button';

function getStatusVariant(
  status?: 'Started' | 'Queued' | 'Success' | 'Failed' | string
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'Success') return 'default';
  if (status === 'Failed') return 'destructive';
  if (status === 'Queued') return 'secondary';
  if (status === 'Started') return 'outline';
  return 'secondary';
}

export default function Executions() {
  const {
    items: runs,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
  } = useInfiniteScroll<
    { page?: number; limit?: number; start?: number; search?: string },
    AgentRunDoc
  >({
    fetchFn: async (params) => {
      const response = await getAgentRuns({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
      });

      if (Array.isArray(response)) {
        return {
          data: response,
          hasMore: false,
          total: response.length,
        };
      }

      return {
        data: response.items,
        hasMore: response.hasMore,
        total: response.total,
      };
    },
    initialParams: {},
    pageSize: 20,
    debounceMs: 300,
    autoLoad: true,
  });

  return (
    <PageLayout
      subtitle="View all executions of your Agents"
      filters={
        <FilterBar
          searchPlaceholder="Search executions using Agent Name"
          searchValue={search}
          onSearchChange={setSearch}
        />
      }
    >
      <GridView
        items={runs}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-4">No executions found.</p>
          </div>
        }
        renderItem={(run) => {
          const duration = calculateDuration(run.start_time ?? null, run.end_time ?? null);
          const timeAgo = formatTimeAgo(run.start_time ?? null);
          const status = run.status || 'Unknown';

          return (
            <ItemCard
              title={run.agent || 'Unknown Agent'}
              description={`Run ID: ${run.name}`}
              status={{
                label: status,
                variant: getStatusVariant(run.status),
              }}
              metadata={[
                { label: 'Duration', value: duration, icon: Zap },
                { label: 'Started', value: timeAgo, icon: Calendar },
              ]}
            />
          );
        }}
        keyExtractor={(run) => run.name}
      />

      {hasMore && (
        <div className="flex justify-center py-8">
          <Button
            onClick={() => loadMore()}
            disabled={loadingMore}
            variant="outline"
          >
            {loadingMore ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Loading...
              </>
            ) : (
              'Load More'
            )}
          </Button>
        </div>
      )}

      {!hasMore && runs.length > 0 && (
        <div className="text-center py-4 text-sm text-muted-foreground">
          {total !== undefined ? `Showing all ${total} executions` : 'No more executions to load'}
        </div>
      )}
    </PageLayout>
  );
}
