import { useCallback } from 'react';
import { Calendar, Zap, Activity, Settings } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { PageLayout, FilterBar, GridView, ItemCard } from '../components/dashboard';
import { usePageData } from '../hooks/dashboard/usePageData';
import { getAgents } from '../services/agentApi';
import type { AgentDoc } from '../types/agent.types';

interface Agent {
  id: string;
  name: string;
  description: string;
  model: string;
  status: 'active' | 'idle' | 'error';
  runs: number;
  lastRun: string;
  category: string;
}

// Map AgentDoc to Agent display type
function mapAgentDocToAgent(doc: AgentDoc): Agent {
  // Determine status based on disabled field
  let status: 'active' | 'idle' | 'error' = 'active';
  if (doc.disabled === 1) {
    status = 'idle';
  }

  // Format last execution date
  const lastRun = doc.last_execution
    ? new Date(doc.last_execution).toLocaleDateString()
    : 'Never';

  return {
    id: doc.name,
    name: doc.agent_name || doc.name,
    description: doc.instructions?.slice(0, 100) || 'No description',
    model: doc.model || 'Unknown',
    status,
    runs: 0, // TODO: Fetch from stats or runs
    lastRun,
    category: 'General', // TODO: Add category field if available
  };
}

const statusOptions = [
  { label: 'All Status', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Idle', value: 'idle' },
  { label: 'Error', value: 'error' },
];

const categoryOptions = [
  { label: 'All Categories', value: 'all' },
  { label: 'Support', value: 'support' },
  { label: 'Analytics', value: 'analytics' },
  { label: 'Content', value: 'content' },
  { label: 'Sales', value: 'sales' },
];

function getStatusVariant(status: Agent['status']) {
  switch (status) {
    case 'active':
      return 'default';
    case 'error':
      return 'destructive';
    default:
      return 'secondary';
  }
}

export function AgentsPage() {
  const navigate = useNavigate();
  
  const fetchAgents = useCallback(async () => {
    const agents = await getAgents();
    return agents.map(mapAgentDocToAgent);
  }, []);

  const { data, search, setSearch, filters, setFilters, loading } = usePageData<Agent>({
    fetchFn: fetchAgents,
    searchFields: ['name', 'description'],
    filterFn: (agent, filters) => {
      if (filters.status && filters.status !== 'all' && agent.status !== filters.status) {
        return false;
      }
      if (filters.category && filters.category !== 'all' && agent.category.toLowerCase() !== filters.category) {
        return false;
      }
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
            {
              label: 'Category',
              value: filters.category || 'all',
              options: categoryOptions,
              onChange: (value) => setFilters({ ...filters, category: value }),
            },
          ]}
        />
      }
    >
      <GridView
        items={data}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={loading}
        renderItem={(agent) => (
          <ItemCard
            title={agent.name}
            description={agent.description}
            status={{
              label: agent.status,
              variant: getStatusVariant(agent.status),
            }}
            metadata={[
              { label: 'Model', value: agent.model },
              { label: 'Runs', value: agent.runs.toLocaleString(), icon: Zap },
              { label: 'Last Run', value: agent.lastRun, icon: Calendar },
            ]}
            actions={[
              {
                icon: Settings,
                label: 'Configure',
                onClick: () => navigate(`/agents/${agent.id}`),
              },
              {
                icon: Activity,
                label: 'View Logs',
                onClick: () => console.log('View Logs', agent.id),
              },
            ]}
            onClick={() => navigate(`/agents/${agent.id}`)}
          />
        )}
        keyExtractor={(agent) => agent.id}
      />
    </PageLayout>
  );
}
