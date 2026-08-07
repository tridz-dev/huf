import { useEffect } from 'react';
import { Calendar, Settings, Database, BookOpen } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, GridView, ItemCard, LoadMoreButton, EmptyState } from '../components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getKnowledgeSources } from '../services/knowledgeApi';
import { formatTimeAgo } from '../utils/time';
import { knowledgeSourceFilterStatuses, knowledgeTypeLabels } from '../data/knowledge';
import type { KnowledgeSourceDoc } from '../types/knowledge.types';

function getStatusVariant(source: KnowledgeSourceDoc): 'default' | 'secondary' | 'destructive' | 'success' | 'outline' {
  if (source.disabled === 1) return 'secondary';
  switch (source.status) {
    case 'Ready':
      return 'success';
    case 'Indexing':
    case 'Rebuilding':
      return 'outline';
    case 'Error':
      return 'destructive';
    default:
      return 'secondary';
  }
}

function getStatusLabel(source: KnowledgeSourceDoc): string {
  if (source.disabled === 1) return 'Disabled';
  return source.status;
}

export { KnowledgeSourcesPage };
export default KnowledgeSourcesPage;

function KnowledgeSourcesPage() {
  const navigate = useNavigate();

  const {
    items: sources,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    filters,
    setFilter,
    loadMore,
    total,
    error,
  } = useInfiniteScroll<
    { status?: string; page?: number; limit?: number; start?: number; search?: string },
    KnowledgeSourceDoc
  >({
    fetchFn: async (params) => {
      const response = await getKnowledgeSources({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: params.status,
      });

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

  useEffect(() => {
    if (error) {
      toast.error('Failed to load knowledge sources', {
        description: error.message || 'An error occurred while fetching knowledge sources.',
        duration: 5000,
      });
    }
  }, [error]);

  return (
    <PageFrame
      filters={
        <FilterBar
          searchPlaceholder="Search knowledge sources..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: [...knowledgeSourceFilterStatuses],
              onChange: (value) => setFilter('status', value),
            },
          ]}
        />
      }
    >
      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load knowledge sources</p>
          <p className="text-sm text-steel mb-4">
            {error.message || 'An error occurred while fetching knowledge sources.'}
          </p>
        </div>
      )}
      <GridView
        items={sources}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          !!search || (filters.status && filters.status !== 'all') ? (
            <EmptyState
              variant="no-results"
              icon={BookOpen}
              title="No knowledge sources found"
              filterTerm={search}
              secondaryAction={{
                label: 'Clear filters',
                onClick: () => {
                  setSearch('');
                  setFilter('status', 'all');
                },
              }}
            />
          ) : (
            <EmptyState
              variant="create"
              icon={BookOpen}
              title="No knowledge sources"
              description="No knowledge sources have been added yet."
              action={{ label: 'New knowledge source', onClick: () => navigate('/knowledge/new') }}
            />
          )
        }
        renderItem={(source) => {
          const statusLabel = getStatusLabel(source);
          return (
            <ItemCard
              title={source.source_name || source.name}
              description={source.description?.slice(0, 100) || 'No description'}
              status={{
                label: statusLabel,
                variant: getStatusVariant(source),
              }}
              metadata={[
                { label: 'Type', value: knowledgeTypeLabels[source.knowledge_type] ?? source.knowledge_type, icon: Database },
                { label: 'Chunks', value: (source.total_chunks ?? 0).toLocaleString() },
                {
                  label: 'Last indexed',
                  value: source.last_indexed_at ? formatTimeAgo(source.last_indexed_at) : 'Never',
                  icon: Calendar,
                },
              ]}
              actions={[
                {
                  icon: Settings,
                  label: 'Configure',
                  onClick: () => navigate(`/knowledge/${source.name}`),
                },
              ]}
              onClick={() => navigate(`/knowledge/${source.name}`)}
            />
          );
        }}
        keyExtractor={(source) => source.name}
      />
      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />
      {!hasMore && sources.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined
            ? `Showing all ${total} knowledge sources`
            : 'No more knowledge sources to load'}
        </div>
      )}
    </PageFrame>
  );
}
