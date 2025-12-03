import { Calendar, Activity, Settings, Zap, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { PageLayout, FilterBar, GridView, ItemCard } from '../components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getAgents } from '../services/agentApi';
import { formatTimeAgo } from '../utils/time';
import type { AgentDoc } from '../types/agent.types';
import { Button } from '../components/ui/button';

const statusOptions = [
  { label: 'All Status', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Disabled', value: 'disabled' },
];

function getStatusVariant(status: 'active' | 'disabled') {
  switch (status) {
    case 'active':
      return 'default';
    case 'disabled':
      return 'secondary';
    default:
      return 'secondary';
  }
}

function getStatusLabel(agent: AgentDoc): 'active' | 'disabled' {
  return agent.disabled === 1 ? 'disabled' : 'active';
}

export function AgentsPage() {
  const navigate = useNavigate();

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
  } = useInfiniteScroll<
    { status?: 'active' | 'disabled' | 'all'; page?: number; limit?: number; start?: number; search?: string },
    AgentDoc
  >({
    fetchFn: async (params) => {
      const response = await getAgents({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: params.status,
      });

      // Handle both old (array) and new (paginated) response formats
      if (Array.isArray(response)) {
        return {
          data: response,
          hasMore: false,
          total: response.length,
        };
      }

      // Convert PaginatedAgentsResponse to PaginatedResponse format
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
      subtitle="Manage your AI agents and their configurations"
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
          ]}
        />
      }
    >
      <GridView
        items={agents}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-4">No agents found.</p>
          </div>
        }
        renderItem={(agent) => {
          const status = getStatusLabel(agent);
          return (
            <ItemCard
              title={agent.agent_name || agent.name}
              description={agent.description?.slice(0, 100) || 'No description'}
              status={{
                label: status,
                variant: getStatusVariant(status),
              }}
              metadata={[
                { label: 'Model', value: agent.model || 'Unknown' },
                { label: 'Runs', value: agent.total_run?.toString() || '0', icon: Zap },
                { label: 'Last Run', value: formatTimeAgo(agent.last_run), icon: Calendar },
              ]}
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
      {!hasMore && agents.length > 0 && (
        <div className="text-center py-4 text-sm text-muted-foreground">
          {total !== undefined ? `Showing all ${total} agents` : 'No more agents to load'}
        </div>
      )}
    </PageLayout>
  );
}
