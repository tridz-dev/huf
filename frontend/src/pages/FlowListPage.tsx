import { useCallback, useState } from 'react';
import { Calendar, Play, Activity, Settings } from 'lucide-react';
import { PageLayout, FilterBar, GridView, ItemCard } from '../components/dashboard';
import { usePageData } from '../hooks/dashboard/usePageData';

import { FlowMetadata } from '../types/flow.types';
import { useNavigate } from 'react-router-dom';
import { getFlowDefinitions, getFlowDefinition } from '../services/flowApi';
import { mapBackendStatusToFrontend } from '../services/flowSerializer';
import { runFlow } from '../services/flowApi';
import { toast } from 'sonner';
import { useFlowContext } from '../contexts/FlowContext';
import { FlowSettingsModal } from '../components/modals/FlowSettingsModal';

const statusOptions = [
  { label: 'All Status', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Draft', value: 'draft' },
  { label: 'Paused', value: 'paused' },
  { label: 'Error', value: 'error' },
];

const categoryOptions = [
  { label: 'All Categories', value: 'all' },
  { label: 'Uncategorized', value: 'uncategorized' },
  { label: 'Automation', value: 'automation' },
  { label: 'Integration', value: 'integration' },
];

function getStatusVariant(status: FlowMetadata['status']) {
  switch (status) {
    case 'active':
      return 'default';
    case 'error':
      return 'destructive';
    case 'paused':
      return 'secondary';
    default:
      return 'outline';
  }
}

export { FlowListPage };
export default FlowListPage;

function FlowListPage() {
  const navigate = useNavigate();
  const { setActiveFlow } = useFlowContext();
  const [showSettings, setShowSettings] = useState(false);

  // Memoize fetchFn with NO dependencies to prevent ANY re-renders
  const fetchFn = useCallback(async () => {
    const items = await getFlowDefinitions();

    // Enrich with metadata (description, category) and nodeCount from definition_json
    const withMetadata = await Promise.all(
      items.map(async (item) => {
        try {
          const def = await getFlowDefinition(item.flow_id);
          const graph = def.definition_json;
          const metadata = graph?.metadata || {};
          const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];

          return {
            id: item.flow_id,
            name: def.flow_name || metadata.name || item.flow_name,
            description: metadata.description,
            status: mapBackendStatusToFrontend(def.status || item.status),
            category: metadata.category,
            nodeCount: nodes.length || 0,
            createdAt: new Date(item.modified),
            updatedAt: new Date(item.modified),
          } as FlowMetadata;
        } catch {
          return {
            id: item.flow_id,
            name: item.flow_name,
            description: undefined,
            status: mapBackendStatusToFrontend(item.status),
            category: undefined,
            nodeCount: 0,
            createdAt: new Date(item.modified),
            updatedAt: new Date(item.modified),
          } as FlowMetadata;
        }
      })
    );

    return withMetadata;
  }, []);

  const { data, loading, search, setSearch, filters, setFilters, refresh } = usePageData<FlowMetadata>({
    fetchFn,
    searchFields: ['name', 'description'],
    filterFn: useCallback((flow: FlowMetadata, filters: Record<string, string>) => {
      if (filters.status && filters.status !== 'all' && flow.status !== filters.status) {
        return false;
      }
      if (filters.category && filters.category !== 'all' && flow.category?.toLowerCase() !== filters.category) {
        return false;
      }
      return true;
    }, []),
  });

  const handleFlowClick = (flowId: string) => {
    // Navigate to the flow canvas
    navigate(`/flows/${flowId}`);
  };

  const handleConfigureFlow = (flowId: string) => {
    // Stay on the list page and open the shared FlowSettingsModal
    setActiveFlow(flowId);
    setShowSettings(true);
  };

  const handleRunFlow = async (flowId: string) => {
    try {
      const result = await runFlow(flowId);
      toast.success('Flow run started', { description: `Run ID: ${result.flow_run_id}` });
    } catch (err) {
      toast.error('Failed to run flow', { description: err instanceof Error ? err.message : 'Unknown error' });
    }
  };

  return (
    <PageLayout
      subtitle="Manage your automated workflows and integrations"
      filters={
        <FilterBar
          searchPlaceholder="Search flows..."
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
        renderItem={(flow) => (
          <ItemCard
            title={flow.name}
            description={flow.description || 'No description'}
            status={{
              label: flow.status,
              variant: getStatusVariant(flow.status),
            }}
            metadata={[
              { label: 'Category', value: flow.category || 'Uncategorized' },
              { label: 'Nodes', value: flow.nodeCount.toString(), icon: Activity },
              {
                label: 'Updated',
                value: new Date(flow.updatedAt).toLocaleDateString(),
                icon: Calendar
              },
            ]}
            actions={[
              {
                icon: Play,
                label: 'Run Flow',
                onClick: () => handleRunFlow(flow.id),
              },
              {
                icon: Settings,
                label: 'Configure',
                onClick: () => handleConfigureFlow(flow.id),
              },
            ]}
            onClick={() => handleFlowClick(flow.id)}
          />
        )}
        keyExtractor={(flow) => flow.id}
      />
      <FlowSettingsModal
        open={showSettings}
        onClose={() => {
          setShowSettings(false);
          // Refresh the list so name/description/category updates are visible without manual reload
          refresh();
        }}
      />
    </PageLayout>
  );
}
