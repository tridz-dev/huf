import { useState, useEffect, useMemo } from 'react';
import { Zap, Calendar, Loader2 } from 'lucide-react';
import { FilterBar, GridView, PageLayout, ItemCard } from '@/components/dashboard';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getAgentRuns, type AgentRunDoc } from '@/services/agentRunApi';
import { formatTimeAgo, calculateDuration } from '@/utils/time';
import { Button } from '@/components/ui/button';
import { getAgentRunStatusVariant } from '@/utils/status';
import { Combobox } from '@/components/ui/combobox';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

export default function Executions() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [agents, setAgents] = useState<Array<{ name: string }>>([]);

  const {
    items: runs,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
    filters,
    setFilter,
  } = useInfiniteScroll<
    { page?: number; limit?: number; start?: number; search?: string; status?: string; agents?: string },
    AgentRunDoc
  >({
    fetchFn: async (params) => {
      const response = await getAgentRuns({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: params.status as any,
        agents: params.agents ? params.agents.split(',').filter(Boolean) : undefined,
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

  // Initialize filters from URL on mount
  useEffect(() => {
    const initialSearch = searchParams.get('q') ?? '';
    const initialStatus = searchParams.get('status') ?? 'all';
    const initialAgents = searchParams.get('agents') ?? 'all';

    if (initialSearch) {
      setSearch(initialSearch);
    }
    if (initialStatus && initialStatus !== (filters.status || 'all')) {
      setFilter('status', initialStatus);
    }
    if (initialAgents && initialAgents !== (filters.agents || 'all')) {
      setFilter('agents', initialAgents);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateSearchParams = (next: { q?: string; status?: string; agents?: string }) => {
    setSearchParams((prev) => {
      const sp = new URLSearchParams(prev);

      if (next.q !== undefined) {
        if (next.q) sp.set('q', next.q);
        else sp.delete('q');
      }

      if (next.status !== undefined) {
        if (next.status && next.status !== 'all') sp.set('status', next.status);
        else sp.delete('status');
      }

      if (next.agents !== undefined) {
        if (next.agents && next.agents !== 'all') sp.set('agents', next.agents);
        else sp.delete('agents');
      }

      return sp;
    });
  };

  // Fetch agents on mount
  useEffect(() => {
    async function fetchAgents() {
      try {
        const agentList = await db.getDocList(doctype.Agent, {
          fields: ['name'],
          limit: 10000, // Fetch all agents
          orderBy: { field: 'name', order: 'asc' },
        });
        setAgents(agentList as Array<{ name: string }>);
      } catch (error) {
        handleFrappeError(error, 'Error fetching agents');
        setAgents([]);
      }
    }
    fetchAgents();
  }, []);

  const statusOptions = [
    { label: 'All Status', value: 'all' },
    { label: 'Started', value: 'Started' },
    { label: 'Queued', value: 'Queued' },
    { label: 'Success', value: 'Success' },
    { label: 'Failed', value: 'Failed' },
  ];

  const agentOptions = useMemo(() => {
    const items = agents.map((agent) => ({
      value: agent.name,
      label: agent.name,
    }));
    return [{ label: 'All Agents', value: 'all' }, ...items];
  }, [agents]);

  const selectedAgentValue = filters.agents || 'all';

  return (
    <PageLayout
      subtitle="View all executions of your Agents"
      filters={
        <FilterBar
          searchPlaceholder="Search executions using Agent Name"
          searchValue={search}
          onSearchChange={(value) => {
            setSearch(value);
            updateSearchParams({ q: value });
          }}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: statusOptions,
              onChange: (value) => {
                setFilter('status', value);
                updateSearchParams({ status: value });
              },
            },
          ]}
          actions={
            <div className="w-48">
              <Combobox
                options={agentOptions}
                value={selectedAgentValue}
                onValueChange={(value) => {
                  if (!value || value === 'all') {
                    setFilter('agents', 'all');
                    updateSearchParams({ agents: 'all' });
                  } else {
                    setFilter('agents', value);
                    updateSearchParams({ agents: value });
                  }
                }}
                placeholder="Filter by agent..."
                emptyText="No agents found."
                searchPlaceholder="Search agents..."
              />
            </div>
          }
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
                variant: getAgentRunStatusVariant(run.status),
              }}
              metadata={[
                { label: 'Duration', value: duration, icon: Zap },
                { label: 'Started', value: timeAgo, icon: Calendar },
              ]}
              onClick={() => navigate(`/executions/${run.name}`)}
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
