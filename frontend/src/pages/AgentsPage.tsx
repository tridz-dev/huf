import { useEffect, type ReactNode } from 'react';
import { Calendar, Activity, Settings, Zap, Server, Lock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { PageLayout, FilterBar, GridView, ItemCard, LoadMoreButton } from '../components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { usePermissions } from '../contexts/PermissionsContext';
import { getAgents } from '../services/agentApi';
import { formatTimeAgo } from '../utils/time';
import type { AgentDoc } from '../types/agent.types';
import { ProviderBrandIcon } from '@/components/providers/ProviderBrandIcon';
import { resolveProviderBrand } from '@/utils/providerBrands';

const statusOptions = [
  { label: 'All Status', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Disabled', value: 'disabled' },
];

const chatOptions = [
  { label: 'All Agents', value: 'all' },
  { label: 'Chat Enabled', value: 'chat' },
  { label: 'Automation Only', value: 'no_chat' },
];

function getStatusVariant(status: 'active' | 'disabled') {
  switch (status) {
    case 'active':
      return 'success';
    case 'disabled':
      return 'secondary';
    default:
      return 'secondary';
  }
}

function getStatusLabel(agent: AgentDoc): 'active' | 'disabled' {
  return agent.disabled === 1 ? 'disabled' : 'active';
}

function getAgentBadges(agent: AgentDoc) {
  const badges: Array<{ label: ReactNode; variant?: 'default' | 'secondary' | 'outline' }> = [];

  if (agent.is_system === 1) {
    badges.push({
      label: (
        <span className="inline-flex items-center gap-1">
          <Lock className="w-3 h-3" />
          System
        </span>
      ),
      variant: 'secondary',
    });
  }
  if (agent.allow_chat === 1) {
    badges.push({ label: 'Chat', variant: 'default' });
  }
  if (agent.prompt_mode === 'Template') {
    badges.push({ label: 'Template', variant: 'secondary' });
  }
  if (agent.enable_multi_run === 1) {
    badges.push({ label: 'Multi-run', variant: 'outline' });
  }
  if (agent.enable_prompt_caching === 1) {
    badges.push({ label: 'Prompt cache', variant: 'outline' });
  }
  if (agent.allow_guest === 1) {
    badges.push({ label: 'Guest', variant: 'outline' });
  }

  return badges;
}

export { AgentsPage };
export default AgentsPage;

function AgentsPage() {
  const navigate = useNavigate();
  const { hufRole } = usePermissions();
  // Backend maps Administrator / System Manager to the "Huf Admin" Huf role.
  const isAdmin = hufRole === 'Huf Admin';

  const {
    items: agents,
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
    {
      status?: 'active' | 'disabled' | 'all';
      chat?: 'all' | 'chat' | 'no_chat';
      page?: number;
      limit?: number;
      start?: number;
      search?: string;
    },
    AgentDoc
  >({
    fetchFn: async (params) => {
      const response = await getAgents({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: params.status,
        chat: params.chat,
      });

      if (Array.isArray(response)) {
        // Defense in depth: backend already excludes system agents for
        // non-admins via permission_query_conditions; filter client-side too.
        const items = isAdmin ? response : response.filter((agent) => agent.is_system !== 1);
        return {
          data: items,
          hasMore: false,
          total: items.length,
        };
      }

      const items = isAdmin ? response.items : response.items.filter((agent) => agent.is_system !== 1);
      return {
        data: items,
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
      toast.error('Failed to load agents', {
        description: error.message || 'An error occurred while fetching agents. Please try again.',
        duration: 5000,
      });
    }
  }, [error]);

  return (
    <PageLayout
      title="Agents"
      subtitle="Create and manage your AI agents."
      filters={
        <FilterBar
          searchPlaceholder="Search agents..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: statusOptions,
              onChange: (value) => setFilter('status', value),
            },
            {
              label: 'Chat',
              value: filters.chat || 'all',
              options: chatOptions,
              onChange: (value) => setFilter('chat', value),
            },
          ]}
        />
      }
    >
      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load agents</p>
          <p className="text-sm text-steel mb-4">{error.message || 'An error occurred while fetching agents.'}</p>
        </div>
      )}
      <GridView
        items={agents}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <div className="text-center py-12">
            <p className="font-body text-steel mb-4">No agents found.</p>
          </div>
        }
        renderItem={(agent) => {
          const status = getStatusLabel(agent);
          const lastActivity = agent.last_run || agent.modified;

          return (
            <ItemCard
              title={agent.agent_name || agent.name}
              description={agent.description?.slice(0, 100) || 'No description'}
              avatarColor={agent.agent_color}
              cornerBadge={
                <ProviderBrandIcon
                  brand={resolveProviderBrand(agent.provider_brand, agent.provider)}
                  size="sm"
                  showFallback
                />
              }
              status={{
                label: status,
                variant: getStatusVariant(status),
              }}
              metadata={[
                { label: 'Provider', value: agent.provider || 'Unknown', icon: Server },
                { label: 'Model', value: agent.model || 'Unknown' },
                { label: 'Runs', value: agent.total_run?.toString() || '0', icon: Zap },
                {
                  label: agent.last_run ? 'Last Run' : 'Updated',
                  value: formatTimeAgo(lastActivity),
                  icon: Calendar,
                },
              ]}
              badges={getAgentBadges(agent)}
              actions={[
                {
                  icon: Settings,
                  label: 'Configure',
                  onClick: () => navigate(`/agents/${agent.name}`),
                },
                {
                  icon: Activity,
                  label: 'View Logs',
                  onClick: () => navigate(`/executions?agents=${encodeURIComponent(agent.name)}`),
                },
              ]}
              onClick={() => navigate(`/agents/${agent.name}`)}
            />
          );
        }}
        keyExtractor={(agent) => agent.name}
      />
      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />
      {!hasMore && agents.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} agents` : 'No more agents to load'}
        </div>
      )}
    </PageLayout>
  );
}
