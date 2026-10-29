import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, Link, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, GridView, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import {
  getIntegrationSettings,
  getIntegrationServices,
} from '@/services/integrationApi';
import { AddIntegrationToAgentModal } from '@/components/integrations/AddIntegrationToAgentModal';
import { ConnectChannelAgentModal } from '@/components/integrations/ConnectChannelAgentModal';
import { ServiceCatalogModal } from '@/components/integrations/ServiceCatalogModal';
import { IntegrationCard } from '@/components/integrations/connection/IntegrationCard';
import { IntegrationStatusPill } from '@/components/integrations/connection/IntegrationStatusPill';
import { CategoryFilter } from '@/components/integrations/connection/CategoryFilter';
import { Button } from '@/components/ui/button';
import type { IntegrationSettingsDoc, IntegrationServiceDoc } from '@/types/integration.types';
import { formatTimeAgo } from '@/utils/time';
import { getServiceIdentity } from '@/data/serviceIdentity';
import { groupInactiveDuplicates, integrationHealth, integrationTitle, sortByHealth } from '@/lib/integrations/health';
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
    return Array.from(unique).sort();
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
      return kind === 'channels' ? isGateway : true;
    });
    const inCategory =
      categoryFilter === 'all' ? byKind : byKind.filter((item) => serviceCategoryMap.get(item.service) === categoryFilter);
    return sortByHealth(inCategory);
  }, [allSettings, categoryFilter, kind, serviceCategoryMap, serviceSurfaceMap]);

  const { visible, groups } = useMemo(() => groupInactiveDuplicates(settings), [settings]);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

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
          actions={<CategoryFilter value={categoryFilter} categories={categories} onChange={setCategoryFilter} />}
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
        items={visible}
        columns={{ sm: 1, md: 2, lg: 2, xl: 3 }}
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
        renderItem={(setting) => (
          <IntegrationCard
            setting={setting}
            onOpen={() => navigate(detailsRoute(setting.name))}
            onUseInAgent={() => {
              setSelectedSetting(setting);
              setAddToAgentOpen(true);
            }}
          />
        )}
        keyExtractor={(setting) => setting.name}
      />

      {groups.length > 0 && (
        <section className="mt-6 space-y-2" data-testid="integration-inactive-groups" aria-label="Not in use">
          <h2 className="text-sm font-medium text-steel">Not in use</h2>
          {groups.map((group) => {
            const open = openGroups[group.service] ?? false;
            const Logo = getServiceIdentity(group.service).icon;
            return (
              <div key={group.service} className="rounded-lg border bg-card" data-testid={`integration-group-${group.service}`}>
                <button
                  type="button"
                  className="flex w-full items-center gap-3 px-4 py-3 text-left"
                  aria-expanded={open}
                  data-testid={`integration-group-toggle-${group.service}`}
                  onClick={() => setOpenGroups((prev) => ({ ...prev, [group.service]: !open }))}
                >
                  <Logo className="h-5 w-5 shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink">
                      {group.title}: {group.items.length} inactive copies
                    </span>
                    <span className="block truncate text-xs text-steel">
                      Switched off and never named. Open one to set it up, or delete the ones you do not need.
                    </span>
                  </span>
                  <ChevronDown className={`h-4 w-4 shrink-0 text-steel transition-transform ${open ? 'rotate-180' : ''}`} />
                </button>
                {open && (
                  <ul className="divide-y border-t">
                    {group.items.map((item) => (
                      <li key={item.name} className="flex items-center gap-3 px-4 py-2 text-sm">
                        <span className="min-w-0 flex-1 truncate">
                          {integrationTitle(item)}
                          <span className="ml-2 text-xs text-steel-soft">edited {formatTimeAgo(item.modified).toLowerCase()}</span>
                        </span>
                        <IntegrationStatusPill health={integrationHealth(item)} />
                        <Button type="button" variant="ghost" size="sm" onClick={() => navigate(detailsRoute(item.name))}>
                          Open
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </section>
      )}

      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading || categoryFilter !== 'all'}
      />

      {!hasMore && settings.length > 0 && categoryFilter === 'all' && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} connection${total === 1 ? '' : 's'}` : 'No more to load'}
        </div>
      )}

      {categoryFilter !== 'all' && settings.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel flex items-center justify-center gap-1">
          <Users className="w-4 h-4" />
          {settings.length} connection{settings.length !== 1 ? 's' : ''} in this category
        </div>
      )}

      {selectedSetting && serviceSurfaceMap?.get(selectedSetting.service.toLowerCase()) === 'Gateway' ? (
        <ConnectChannelAgentModal
          open={addToAgentOpen}
          onOpenChange={(open) => {
            setAddToAgentOpen(open);
            if (!open) setSelectedSetting(null);
          }}
          integrationName={selectedSetting.name}
        />
      ) : (
        <AddIntegrationToAgentModal
          open={addToAgentOpen}
          onOpenChange={(open) => {
            setAddToAgentOpen(open);
            if (!open) setSelectedSetting(null);
          }}
          service={selectedSetting?.service || ''}
          integrationName={selectedSetting?.name}
        />
      )}
    </PageFrame>
  );
}

export default IntegrationSettingsListingPage;
