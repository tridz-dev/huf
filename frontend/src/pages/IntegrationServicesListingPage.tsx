import { useEffect } from 'react';
import { Puzzle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, GridView, ItemCard, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { CategoryFilter } from '@/components/integrations/connection/CategoryFilter';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { getIntegrationServicesPaginated } from '@/services/integrationApi';
import { integrationCategoryFilterOptions } from '@/data/integrations';
import type { IntegrationServiceDoc } from '@/types/integration.types';
import { getServiceIdentity } from '@/data/serviceIdentity';

export function IntegrationServicesListingPage() {
  const navigate = useNavigate();

  const {
    items: services,
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
    { category?: string; page?: number; limit?: number; start?: number; search?: string },
    IntegrationServiceDoc
  >({
    fetchFn: async (params) => {
      const response = await getIntegrationServicesPaginated({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        category: params.category,
      });

      return {
        data: response.items,
        hasMore: response.hasMore,
        total: response.total,
      };
    },
    initialParams: { category: 'all' },
    pageSize: 20,
    debounceMs: 300,
    autoLoad: true,
  });

  const categoryFilter = filters.category ?? 'all';

  useEffect(() => {
    if (error) {
      toast.error('Failed to load integration services', {
        description: error.message || 'An error occurred while fetching integration services.',
      });
    }
  }, [error]);

  return (
    <PageFrame
      filters={
        <FilterBar
          searchPlaceholder="Search services..."
          searchValue={search}
          onSearchChange={setSearch}
          actions={
            <CategoryFilter
              value={categoryFilter}
              categories={integrationCategoryFilterOptions.filter((o) => o.value !== 'all').map((o) => o.value)}
              onChange={(value) => setFilter('category', value)}
            />
          }
        />
      }
    >
      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load integration services</p>
          <p className="text-sm text-steel">{error.message}</p>
        </div>
      )}

      <GridView
        items={services}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          search || categoryFilter !== 'all' ? (
            <EmptyState
              variant="no-results"
              icon={Puzzle}
              title="No integration services found"
              filterTerm={search}
              secondaryAction={{
                label: 'Clear filters',
                onClick: () => {
                  setSearch('');
                  setFilter('category', 'all');
                },
              }}
            />
          ) : (
            <EmptyState
              variant="create"
              icon={Puzzle}
              title="No integration services"
              description="Define a service catalog to describe credentials and connection settings."
              action={{ label: 'New service', onClick: () => navigate('/integration-services/new') }}
            />
          )
        }
        renderItem={(service) => {
          const identity = getServiceIdentity(service.service_name);
          return (
            <ItemCard
              title={identity.title}
              icon={identity.icon}
              description={service.description || 'No description'}
              badges={[
                ...(service.category ? [{ label: service.category, variant: 'secondary' as const }] : []),
                ...(service.is_builtin ? [] : [{ label: 'Custom', variant: 'outline' as const }]),
              ]}
              onClick={() =>
                navigate(`/integration-services/${encodeURIComponent(service.service_name)}`)
              }
            />
          );
        }}
        keyExtractor={(service) => service.name}
      />

      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />

      {!hasMore && services.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} services` : 'No more services to load'}
        </div>
      )}
    </PageFrame>
  );
}

export default IntegrationServicesListingPage;
