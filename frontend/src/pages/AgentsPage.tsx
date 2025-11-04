import { useCallback } from 'react';
import { Calendar, Activity, Settings } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { PageLayout, FilterBar, GridView, ItemCard } from '../components/dashboard';
import { usePageData } from '../hooks/dashboard/usePageData';
import { getAgents } from '../services/agentApi';
import type { AgentDoc } from '../types/agent.types';

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

function formatLastExecution(lastExecution: string | null): string {
  if (!lastExecution) return 'Never';
  try {
    return new Date(lastExecution).toLocaleDateString();
  } catch {
    return 'Never';
  }
}

export function AgentsPage() {
  const navigate = useNavigate();
  
  const fetchAgents = useCallback(async () => {
    const agents = await getAgents();
    return agents;
  }, []);

  const { data, search, setSearch, filters, setFilters, loading } = usePageData<AgentDoc>({
    fetchFn: fetchAgents,
    searchFields: ['agent_name', 'instructions'],
    filterFn: (agent, filters) => {
      if (filters.status && filters.status !== 'all') {
        const agentStatus = getStatusLabel(agent);
        if (agentStatus !== filters.status) {
          return false;
        }
      }
      // Category filter can be added when category field is available
      return true;
    },
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
              onChange: (value) => setFilters({ ...filters, status: value }),
            },
          ]}
        />
      }
    >
      <GridView
        items={data}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={loading}
        renderItem={(agent) => {
          const status = getStatusLabel(agent);
          return (
            <ItemCard
              title={agent.agent_name || agent.name}
              description={agent.instructions?.slice(0, 100) || 'No description'}
              status={{
                label: status,
                variant: getStatusVariant(status),
              }}
              metadata={[
                { label: 'Model', value: agent.model || 'Unknown' },
                { label: 'Last Run', value: formatLastExecution(agent.last_execution), icon: Calendar },
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
                  onClick: () => console.log('View Logs', agent.name),
                },
              ]}
              onClick={() => navigate(`/agents/${agent.name}`)}
            />
          );
        }}
        keyExtractor={(agent) => agent.name}
      />
    </PageLayout>
  );
}
