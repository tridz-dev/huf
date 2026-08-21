import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Bot, Link, Settings, Star, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, GridView, ItemCard, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import {
  getIntegrationSettings,
  getIntegrationServices,
} from '@/services/integrationApi';
import { AddIntegrationToAgentModal } from '@/components/integrations/AddIntegrationToAgentModal';
import { ServiceCatalogModal } from '@/components/integrations/ServiceCatalogModal';
import { ServiceToolCount } from '@/components/integrations/ServiceToolCount';
import type { IntegrationSettingsDoc, IntegrationServiceDoc } from '@/types/integration.types';
import { formatTimeAgo } from '@/utils/time';
import { getServiceIdentity } from '@/data/serviceIdentity';
import { getServiceSurfaceMap, type ServiceSurface } from '@/services/serviceSurfaceCache';

interface IntegrationSettingsListingPageProps {
  catalogOpenKey?: number;
  kind?: 'channels' | 'integrations';
}

export function IntegrationSettingsListingPage({
  catalogOpenKey,
  kind = 'integrations',
}: IntegrationSettingsListingPageProps) {
  const navigate = useNavigate();
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [services, setServices] = useState<IntegrationServiceDoc[]>([]);
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [addToAgentOpen, setAddToAgentOpen] = useState(false);
  const [selectedSetting, setSelectedSetting] = useState<IntegrationSettingsDoc | null>(null);
  const [serviceSurfaceMap, setServiceSurfaceMap] = useState<Map<string, ServiceSurface> | null>(null);

  useEffect(() => {
    getIntegrationServices().then(setServices).catch(() => {
      // Non-fatal; cards still render without category labels
    });
  }, []);

  useEffect(() => {
    getServiceSurfaceMap().then(setServiceSurfaceMap).catch(() => {
      // Non-fatal; defaults to treating every service as an Integration
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

  const detailsRoute = (name: string) =>
    `${kind === 'channels' ? '/gateways' : '/integrations'}/${encodeURIComponent(name)}`;

  const settings = useMemo(() => {
    const byKind = allSettings.filter((item) => {
      const surface = serviceSurfaceMap?.get(item.service.toLowerCase()) || 'Integration';
      const isGateway = surface === 'Gateway';
      return kind === 'channels' ? isGateway : !isGateway;
    });
    if (categoryFilter === 'all') return byKind;
    return byKind.filter((item) => serviceCategoryMap.get(item.service) === categoryFilter);
  }, [allSettings, categoryFilter, kind, serviceCategoryMap, serviceSurfaceMap]);

  useEffect(() => {
    if (error) {
      toast.error('Failed to load integrations', {
        description: error.message || 'An error occurred while fetching integrations.',
      });
    }
  }, [error]);

  return (
    <PageFrame
      filters={
        <FilterBar
          searchPlaceholder={kind === 'channels' ? 'Search channels...' : 'Search integrations...'}
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
      <ServiceCatalogModal open={catalogOpen} onOpenChange={setCatalogOpen} kind={kind} />

      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load integrations</p>
          <p className="text-sm text-steel">{error.message}</p>
        </div>
      )}

      <GridView
        items={settings}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          search || categoryFilter !== 'all' ? (
            <EmptyState
              variant="no-results"
              icon={Link}
              title={kind === 'channels' ? 'No channels found' : 'No integrations found'}
              filterTerm={search}
              secondaryAction={{
                label: 'Clear filters',
                onClick: () => {
                  setSearch('');
                  setCategoryFilter('all');
                },
              }}
            />
          ) : (
            <EmptyState
              variant="create"
              icon={Link}
              title={kind === 'channels' ? 'No channels' : 'No integrations'}
              description={
                kind === 'channels'
                  ? 'No messaging channels have been connected yet.'
                  : 'No integrations have been connected yet.'
              }
              action={{
                label: kind === 'channels' ? 'Add channel' : 'Add integration',
                onClick: () => setCatalogOpen(true),
              }}
            />
          )
        }
        renderItem={(setting) => {
          const category = serviceCategoryMap.get(setting.service);
          const identity = getServiceIdentity(setting.service);
          const metadata = [
            ...(category ? [{ label: 'Category', value: category }] : []),
            { label: 'Tools', value: <ServiceToolCount service={setting.service} /> },
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
              description={`${identity.title} ${kind === 'channels' ? 'channel' : 'integration'}`}
              icon={identity.icon}
              status={{
                label: setting.is_active ? 'active' : 'inactive',
                variant: setting.is_active ? 'default' : 'secondary',
              }}
              metadata={metadata}
              actions={[
                {
                  icon: Bot,
                  label: 'Add to Agent',
                  onClick: () => {
                    setSelectedSetting(setting);
                    setAddToAgentOpen(true);
                  },
                },
                {
                  icon: Settings,
                  label: 'Configure',
                  onClick: () => navigate(detailsRoute(setting.name)),
                },
              ]}
              onClick={() => navigate(detailsRoute(setting.name))}
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
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} integrations` : 'No more integrations to load'}
        </div>
      )}

      {categoryFilter !== 'all' && settings.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel flex items-center justify-center gap-1">
          <Users className="w-4 h-4" />
          {settings.length} integration{settings.length !== 1 ? 's' : ''} in this category
        </div>
      )}

      <AddIntegrationToAgentModal
        open={addToAgentOpen}
        onOpenChange={(open) => {
          setAddToAgentOpen(open);
          if (!open) setSelectedSetting(null);
        }}
        service={selectedSetting?.service || ''}
        integrationName={selectedSetting?.name}
      />
    </PageFrame>
  );
}

export default IntegrationSettingsListingPage;
