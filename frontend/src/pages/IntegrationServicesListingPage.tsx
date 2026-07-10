import { useEffect } from 'react';
import { Calendar, KeyRound, Settings, Shield } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { PageLayout, FilterBar, GridView, ItemCard, LoadMoreButton } from '@/components/dashboard';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { getIntegrationServicesPaginated } from '@/services/integrationApi';
import { integrationCategoryFilterOptions } from '@/data/integrations';
import { parseRequiredCredentials } from '@/types/integration.types';
import type { IntegrationServiceDoc } from '@/types/integration.types';
import { formatTimeAgo } from '@/utils/time';

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
    <PageLayout
      subtitle="Define integration service catalogs and credential schemas used by Integration Settings"
      filters={
        <FilterBar
          searchPlaceholder="Search services..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Category',
              value: categoryFilter,
              placeholder: 'Category',
              options: integrationCategoryFilterOptions,
              onChange: (value) => setFilter('category', value),
            },
          ]}
        />
      }
    >
      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load integration services</p>
          <p className="text-sm text-muted-foreground">{error.message}</p>
        </div>
      )}

      <GridView
        items={services}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-4">No integration services found.</p>
            <button
              type="button"
              className="text-sm text-primary hover:underline"
              onClick={() => navigate('/integration-services/new')}
            >
              Create your first service
            </button>
          </div>
        }
        renderItem={(service) => {
          const credentialCount = parseRequiredCredentials(service.required_credentials).length;
          const metadata = [
            { label: 'Category', value: service.category },
            {
              label: 'Credentials',
              value: `${credentialCount} field${credentialCount !== 1 ? 's' : ''}`,
              icon: KeyRound,
            },
            ...(service.is_builtin
              ? [{ label: 'Type', value: 'Built-in', icon: Shield }]
              : []),
            ...(service.modified
              ? [{ label: 'Updated', value: formatTimeAgo(service.modified), icon: Calendar }]
              : []),
          ];

          return (
            <ItemCard
              title={service.service_name.replace(/_/g, ' ')}
              description={service.description || 'No description'}
              status={{
                label: service.is_builtin ? 'built-in' : 'custom',
                variant: service.is_builtin ? 'outline' : 'default',
              }}
              metadata={metadata}
              actions={[
                {
                  icon: Settings,
                  label: 'Configure',
                  onClick: () =>
                    navigate(`/integration-services/${encodeURIComponent(service.service_name)}`),
                },
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
        <div className="text-center py-4 text-sm text-muted-foreground">
          {total !== undefined ? `Showing all ${total} services` : 'No more services to load'}
        </div>
      )}
    </PageLayout>
  );
}

export default IntegrationServicesListingPage;
