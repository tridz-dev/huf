import { Calendar, Zap, Activity, Settings } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { PageLayout, FilterBar, GridView, ItemCard } from '../components/dashboard';
import { usePageData } from '../hooks/dashboard/usePageData';

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

const agents: Agent[] = [
  {
    id: '1',
    name: 'Customer Support Agent',
    description: 'Handles customer inquiries and provides support',
    model: 'GPT-4',
    status: 'active',
    runs: 1247,
    lastRun: '2 minutes ago',
    category: 'Support',
  },
  {
    id: '2',
    name: 'Data Analyst Agent',
    description: 'Analyzes data and generates insights',
    model: 'Claude 3 Opus',
    status: 'active',
    runs: 856,
    lastRun: '15 minutes ago',
    category: 'Analytics',
  },
  {
    id: '3',
    name: 'Content Writer Agent',
    description: 'Creates and optimizes content',
    model: 'GPT-4 Turbo',
    status: 'idle',
    runs: 423,
    lastRun: '3 hours ago',
    category: 'Content',
  },
  {
    id: '4',
    name: 'Sales Assistant Agent',
    description: 'Qualifies leads and schedules meetings',
    model: 'GPT-4',
    status: 'active',
    runs: 672,
    lastRun: '5 minutes ago',
    category: 'Sales',
  },
  {
    id: '5',
    name: 'Research Agent',
    description: 'Conducts research and summarizes findings',
    model: 'Claude 3 Sonnet',
    status: 'idle',
    runs: 234,
    lastRun: '1 day ago',
    category: 'Research',
  },
  {
    id: '6',
    name: 'Code Review Agent',
    description: 'Reviews code and suggests improvements',
    model: 'GPT-4 Turbo',
    status: 'error',
    runs: 189,
    lastRun: '2 days ago',
    category: 'Development',
  },
];

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
  const { data, search, setSearch, filters, setFilters } = usePageData<Agent>({
    initialData: agents,
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
