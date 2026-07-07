import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Settings, Star, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { PageLayout, FilterBar, GridView, ItemCard, LoadMoreButton } from '@/components/dashboard';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import {
  getIntegrationSettings,
  getIntegrationServices,
} from '@/services/integrationApi';
import { ServiceCatalogModal } from '@/components/integrations/ServiceCatalogModal';
import type { IntegrationSettingsDoc, IntegrationServiceDoc } from '@/types/integration.types';
import { formatTimeAgo } from '@/utils/time';

interface IntegrationSettingsListingPageProps {
  catalogOpenKey?: number;
}

export function IntegrationSettingsListingPage({
  catalogOpenKey,
}: IntegrationSettingsListingPageProps) {
  const navigate = useNavigate();
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [services, setServices] = useState<IntegrationServiceDoc[]>([]);
  const [categoryFilter, setCategoryFilter] = useState('all');

  useEffect(() => {
    getIntegrationServices().then(setServices).catch(() => {
      // Non-fatal; cards still render without category labels
    });
  }, []);

  useEffect(() => {
    if (catalogOpenKey && catalogOpenKey > 0) {
      setCatalogOpen(true);
    }
  }, [catalogOpenKey]);

  const serviceCategoryMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const service of services) {
      map.set(service.service_name, service.category);
    }
    return map;
  }, [services]);

  const categories = useMemo(() => {
    const unique = new Set(services.map((s) => s.category).filter(Boolean));
    return [
      { label: 'All categories', value: 'all' },
      ...Array.from(unique).sort().map((c) => ({ label: c, value: c })),
    ];
  }, [services]);

  const {
    items: allSettings,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
    error,
  } = useInfiniteScroll<
    { page?: number; limit?: number; start?: number; search?: string },
    IntegrationSettingsDoc
  >({
    fetchFn: async (params) => {
      const response = await getIntegrationSettings({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
      });

      if (Array.isArray(response)) {
        return { data: response, hasMore: false, total: response.length };
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

  const settings = useMemo(() => {
    if (categoryFilter === 'all') return allSettings;
    return allSettings.filter(
      (item) => serviceCategoryMap.get(item.service) === categoryFilter,
    );
  }, [allSettings, categoryFilter, serviceCategoryMap]);

  useEffect(() => {
    if (error) {
      toast.error('Failed to load integrations', {
        description: error.message || 'An error occurred while fetching integrations.',
      });
    }
  }, [error]);

  return (
    <PageLayout
      subtitle="Connect external services like Slack, Telegram, GitHub, and Google Workspace"
      filters={
        <FilterBar
          searchPlaceholder="Search integrations..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Category',
              value: categoryFilter,
              placeholder: 'Category',
              options: categories,
              onChange: setCategoryFilter,
            },
          ]}
        />
      }
    >
      <ServiceCatalogModal open={catalogOpen} onOpenChange={setCatalogOpen} />

      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load integrations</p>
          <p className="text-sm text-muted-foreground">{error.message}</p>
        </div>
      )}

      <GridView
        items={settings}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-4">No integrations configured yet.</p>
            <button
              type="button"
              className="text-sm text-primary hover:underline"
              onClick={() => setCatalogOpen(true)}
            >
              Add your first integration
            </button>
          </div>
        }
        renderItem={(setting) => {
          const category = serviceCategoryMap.get(setting.service);
          const metadata = [
            ...(category ? [{ label: 'Category', value: category }] : []),
            ...(setting.is_default ? [{ label: 'Default', value: 'Yes', icon: Star }] : []),
            ...(setting.last_used
              ? [{ label: 'Last used', value: formatTimeAgo(setting.last_used) }]
              : []),
            ...(setting.last_error
              ? [{ label: 'Error', value: setting.last_error.slice(0, 40), icon: AlertCircle }]
              : []),
          ];

          return (
            <ItemCard
              title={setting.name}
              description={`${setting.service.replace(/_/g, ' ')} integration`}
              status={{
                label: setting.is_active ? 'active' : 'inactive',
                variant: setting.is_active ? 'default' : 'secondary',
              }}
              metadata={metadata}
              actions={[
                {
                  icon: Settings,
                  label: 'Configure',
                  onClick: () => navigate(`/integrations/${encodeURIComponent(setting.name)}`),
                },
              ]}
              onClick={() => navigate(`/integrations/${encodeURIComponent(setting.name)}`)}
            />
          );
        }}
        keyExtractor={(setting) => setting.name}
      />

      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading || categoryFilter !== 'all'}
      />

      {!hasMore && settings.length > 0 && categoryFilter === 'all' && (
        <div className="text-center py-4 text-sm text-muted-foreground">
          {total !== undefined ? `Showing all ${total} integrations` : 'No more integrations to load'}
        </div>
      )}

      {categoryFilter !== 'all' && settings.length > 0 && (
        <div className="text-center py-4 text-sm text-muted-foreground flex items-center justify-center gap-1">
          <Users className="w-4 h-4" />
          {settings.length} integration{settings.length !== 1 ? 's' : ''} in this category
        </div>
      )}
    </PageLayout>
  );
}

export default IntegrationSettingsListingPage;
