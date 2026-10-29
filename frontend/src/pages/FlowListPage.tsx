import { FlowsListHeaderActions } from '../components/FlowsListHeaderActions';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Calendar, Play, Activity, Settings, Workflow } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, GridView, ItemCard, EmptyState } from '../components/dashboard';
import { ExperimentalBadge } from '../components/common/ExperimentalBadge';
import { usePageData } from '../hooks/dashboard/usePageData';

import { FlowMetadata } from '../types/flow.types';
import { useNavigate } from 'react-router-dom';
import { getFlowDefinitions, getFlowDefinition, FLOW_LIST_LIMIT, type FlowListQuery } from '../services/flowApi';
import { mapBackendStatusToFrontend } from '../services/flowSerializer';
import { runFlow } from '../services/flowApi';
import { toast } from '@/lib/toast';
import { reportFlowRun } from '@/lib/flow-run/flowRunToast';
import { humanizeFlowError } from '@/lib/flow-graph/flowValidation';
import { useFlowContext } from '../contexts/FlowContext';
import { RunFlowDialog } from '../components/flow/RunFlowDialog';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { FLOW_GUIDE_URL } from '@/lib/flow/flowHelp';
import { FlowSettingsModal } from '../components/modals/FlowSettingsModal';

const statusOptions = [
  { label: 'All status', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Draft', value: 'draft' },
  { label: 'Paused', value: 'paused' },
  { label: 'Error', value: 'error' },
];

const categoryOptions = [
  { label: 'All categories', value: 'all' },
  { label: 'Uncategorized', value: 'uncategorized' },
  { label: 'Automation', value: 'automation' },
  { label: 'Integration', value: 'integration' },
  { label: 'Support', value: 'support' },
  { label: 'Sales', value: 'sales' },
  { label: 'Huf Demo', value: 'huf demo' },
];

function getStatusVariant(status: FlowMetadata['status']) {
  switch (status) {
    case 'active':
      return 'success';
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
  const { setActiveFlow, createFlow } = useFlowContext();
  const [showSettings, setShowSettings] = useState(false);
  const [runTarget, setRunTarget] = useState<{ id: string; name: string } | null>(null);
  const { canCreate, canManage } = useFlowPermissions();

  // What the server is asked for: with hundreds of flows, search and filters must reach the server or older flows
  // could never be found. (The page still filters the loaded rows too, so the list answers instantly while typing.)
  const [serverQuery, setServerQuery] = useState<FlowListQuery>({});
  const fetchFn = useCallback(async () => {
    const items = await getFlowDefinitions(serverQuery);

    // Enrich with metadata (description, category) and nodeCount from definition_json
    const withMetadata = await Promise.all(
      items.map(async (item) => {
        try {
          const def = await getFlowDefinition(item.flow_id);
          const graph = def.definition_json;
          // The shared graph-IR carries no `metadata` any more (additionalProperties:
          // false) -- name/description/category live on the Flow Definition doctype
          // record itself, not inside definition_json. See flowSerializer.ts.
          const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];

          return {
            id: item.flow_id,
            name: def.flow_name || item.flow_name,
            description: def.description || undefined,
            status: mapBackendStatusToFrontend(def.status || item.status),
            category: def.category || 'Uncategorized',
            nodeCount: nodes.length || 0,
            createdAt: new Date(item.modified),
            updatedAt: new Date(item.modified),
          } as FlowMetadata;
        } catch {
          return {
            id: item.flow_id,
            name: item.flow_name,
            description: item.description || undefined,
            status: mapBackendStatusToFrontend(item.status),
            category: item.category || 'Uncategorized',
            nodeCount: 0,
            createdAt: new Date(item.modified),
            updatedAt: new Date(item.modified),
          } as FlowMetadata;
        }
      })
    );

    return withMetadata;
  }, [serverQuery]);

  const { data, allData, loading, search, setSearch, filters, setFilters, refresh } = usePageData<FlowMetadata>({
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

  // Ask the server again a moment after the search text or a filter changes (not on first render).
  const firstQuery = useRef(true);
  useEffect(() => {
    const category = filters.category && filters.category !== 'all' && filters.category !== 'uncategorized'
      ? categoryOptions.find((c) => c.value === filters.category)?.label
      : undefined;
    const status = filters.status && filters.status !== 'all'
      ? ({ active: 'Active', draft: 'Draft', paused: 'Archived' } as Record<string, string>)[filters.status]
      : undefined;
    const next: FlowListQuery = { search: search.trim() || undefined, status, category };
    const timer = setTimeout(() => setServerQuery((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next)), 300);
    return () => clearTimeout(timer);
  }, [search, filters.category, filters.status]);
  useEffect(() => {
    if (firstQuery.current) {
      firstQuery.current = false;
      return;
    }
    void refresh();
    // refresh follows fetchFn, which follows serverQuery
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverQuery]);

  const handleFlowClick = (flowId: string) => {
    // Navigate to the flow canvas
    navigate(`/flows/${flowId}`);
  };

  const handleConfigureFlow = (flowId: string) => {
    // Stay on the list page and open the shared FlowSettingsModal
    setActiveFlow(flowId);
    setShowSettings(true);
  };

  const handleRunFlow = async (payload: Record<string, unknown>) => {
    if (!runTarget) return;
    try {
      reportFlowRun(await runFlow(runTarget.id, payload));
    } catch (err) {
      toast.error('Could not run the flow', { description: humanizeFlowError(err) });
    }
  };

  const handleNewFlow = async () => {
    try {
      const newFlow = await createFlow('New Flow', 'Uncategorized');
      navigate(`/flows/${newFlow.id}`);
    } catch (err) {
      toast.error('Could not create the flow', {
        description: humanizeFlowError(err),
      });
    }
  };

  const isFiltered =
    !!search || (filters.status && filters.status !== 'all') || (filters.category && filters.category !== 'all');
  const handleClearFilters = () => {
    setSearch('');
    setFilters({});
  };

  return (
    <PageFrame
      title="Flows"
      badge={<ExperimentalBadge />}
      actions={<FlowsListHeaderActions />}
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
      {allData.length >= FLOW_LIST_LIMIT && (
        <p className="mb-3 text-xs text-muted-foreground" data-testid="flow-list-limit-note">
          Showing the {FLOW_LIST_LIMIT} flows changed most recently. Search or use the filters to find others.
        </p>
      )}
      <GridView
        items={data}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={loading}
        emptyState={
          isFiltered ? (
            <EmptyState
              variant="no-results"
              icon={Workflow}
              title="No flows found"
              filterTerm={search}
              secondaryAction={{ label: 'Clear filters', onClick: handleClearFilters }}
            />
          ) : (
            <EmptyState
              variant="create"
              icon={Workflow}
              title="No flows yet"
              description={canCreate ? 'A flow starts from a trigger, such as a webhook or a schedule, then runs steps one after another. Create your first flow to try it.' : 'No flows have been shared with you yet. Ask a teammate to share one, or ask your administrator for access to create flows.'}
              action={canCreate ? { label: 'New flow', onClick: handleNewFlow } : undefined}
              secondaryAction={{ label: 'How flows work', onClick: () => window.open(FLOW_GUIDE_URL, '_blank', 'noopener') }}
            />
          )
        }
        renderItem={(flow) => (
          <div data-testid={`flow-list-item-${flow.id}`} title={flow.description || undefined}>
          <ItemCard
            title={flow.name}
            description={flow.description || 'No description'}
            status={{
              label: flow.status,
              variant: getStatusVariant(flow.status),
            }}
            metadata={[
              { label: 'Category', value: flow.category || 'Uncategorized' },
              { label: 'Steps', value: flow.nodeCount.toString(), icon: Activity },
              {
                label: 'Updated',
                value: new Date(flow.updatedAt).toLocaleDateString(),
                icon: Calendar
              },
            ]}
            actions={[
              ...(canManage
                ? [{ icon: Play, label: 'Run flow', onClick: () => setRunTarget({ id: flow.id, name: flow.name }) }]
                : []),
              {
                icon: Settings,
                label: canManage ? 'Configure' : 'Settings',
                onClick: () => handleConfigureFlow(flow.id),
              },
            ]}
            onClick={() => handleFlowClick(flow.id)}
          />
          </div>
        )}
        keyExtractor={(flow) => flow.id}
      />
      <RunFlowDialog
        open={!!runTarget}
        flowId={runTarget?.id ?? null}
        flowName={runTarget?.name}
        onOpenChange={(open) => !open && setRunTarget(null)}
        onRun={handleRunFlow}
      />
      <FlowSettingsModal
        open={showSettings}
        onClose={() => {
          setShowSettings(false);
          // Refresh the list so name/description/category updates are visible without manual reload
          refresh();
        }}
      />
    </PageFrame>
  );
}
