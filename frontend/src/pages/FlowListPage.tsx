import { useCallback, useEffect, useRef, useState } from 'react';
import { Workflow } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { PageFrame } from '@/layouts/PageFrame';
import { GridView, EmptyState } from '../components/dashboard';
import { LoadMoreButton } from '../components/dashboard/LoadMoreButton';
import { ExperimentalBadge } from '../components/common/ExperimentalBadge';
import { FlowsListHeaderActions } from '../components/FlowsListHeaderActions';
import { Button } from '../components/ui/button';
import { toast } from '@/lib/toast';
import { reportFlowRun } from '@/lib/flow-run/flowRunToast';
import { humanizeFlowError } from '@/lib/flow-graph/flowValidation';
import { FLOW_GUIDE_URL } from '@/lib/flow/flowHelp';
import { runFlow } from '../services/flowApi';
import {
  cloneFlow, listFlowCards, listFlowCategories, type FlowCard as FlowCardData, type FlowListSort,
} from '../services/flow/flowCardsApi';
import { useFlowContext } from '../contexts/FlowContext';
import { RunFlowDialog } from '../components/flow/RunFlowDialog';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { FlowSettingsModal } from '../components/modals/FlowSettingsModal';
import { FlowCard } from '../components/flow/list/FlowCard';
import { FlowListFilters, type FilterChoice } from '../components/flow/list/FlowListFilters';
import { FirstFlowCoach } from '../components/flow/list/FirstFlowCoach';
import { NewFlowDialog } from '../components/flow/list/NewFlowDialog';
import { DeleteFlowDialog } from '../components/flow/list/DeleteFlowDialog';

/** One word for each stored status (what people read: Draft / Live). */
const STATUS_OPTIONS: FilterChoice[] = [
  { label: 'All statuses', value: 'all' },
  { label: 'Live', value: 'Active' },
  { label: 'Draft', value: 'Draft' },
];

const SORT_OPTIONS: FilterChoice[] = [
  { label: 'Recently updated', value: 'recent' },
  { label: 'Name A to Z', value: 'name' },
];

const BASE_CATEGORIES = ['Automation', 'Integration', 'Support', 'Sales'];
const PAGE_SIZE = 100;

export { FlowListPage };
export default FlowListPage;

function FlowListPage() {
  const navigate = useNavigate();
  const { setActiveFlow, deleteFlow } = useFlowContext();
  const { canCreate, canManage } = useFlowPermissions();

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [category, setCategory] = useState('all');
  const [sort, setSort] = useState<FlowListSort>('recent');
  const [usedCategories, setUsedCategories] = useState<string[]>([]);

  const [items, setItems] = useState<FlowCardData[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [failed, setFailed] = useState(false);

  const [showSettings, setShowSettings] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [runTarget, setRunTarget] = useState<{ id: string; name: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string; live: boolean } | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Newest answer wins: typing quickly must never let a slow older answer overwrite a newer one.
  const requestId = useRef(0);
  const load = useCallback(
    async (debounced: boolean) => {
      const mine = ++requestId.current;
      try {
        const result = await listFlowCards({
          search: debounced ? search.trim() || undefined : undefined,
          status: status === 'all' ? undefined : status,
          category: category === 'all' ? undefined : category,
          sort,
          limit: PAGE_SIZE,
        });
        if (mine !== requestId.current) return;
        setItems(result.items);
        setTotal(result.total);
        setFailed(false);
      } catch {
        if (mine === requestId.current) setFailed(true);
      } finally {
        if (mine === requestId.current) setLoading(false);
      }
    },
    [search, status, category, sort],
  );

  const firstLoad = useRef(true);
  useEffect(() => {
    const wait = firstLoad.current ? 0 : 250;
    firstLoad.current = false;
    const timer = setTimeout(() => void load(true), wait);
    return () => clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    void listFlowCategories().then(setUsedCategories);
  }, []);

  const refresh = () => {
    void load(true);
    void listFlowCategories().then(setUsedCategories);
  };

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const more = await listFlowCards({
        search: search.trim() || undefined,
        status: status === 'all' ? undefined : status,
        category: category === 'all' ? undefined : category,
        sort,
        limit: PAGE_SIZE,
        start: items.length,
      });
      setItems((prev) => [...prev, ...more.items.filter((m) => !prev.some((p) => p.flow_id === m.flow_id))]);
      setTotal(more.total);
    } catch (err) {
      toast.error('Could not load more flows', { description: humanizeFlowError(err) });
    } finally {
      setLoadingMore(false);
    }
  };

  const categoryOptions: FilterChoice[] = [
    { label: 'All categories', value: 'all' },
    { label: 'Uncategorized', value: 'Uncategorized' },
    ...[...new Set([...BASE_CATEGORIES, ...usedCategories])]
      .filter((c) => c.toLowerCase() !== 'uncategorized')
      .sort((a, b) => a.localeCompare(b))
      .map((c) => ({ label: c, value: c })),
  ];

  const isFiltered = !!search.trim() || status !== 'all' || category !== 'all';
  const clearFilters = () => {
    setSearch('');
    setStatus('all');
    setCategory('all');
  };

  const handleRun = async (payload: Record<string, unknown>) => {
    if (!runTarget) return;
    try {
      reportFlowRun(await runFlow(runTarget.id, payload));
      refresh();
    } catch (err) {
      toast.error('Could not run the flow', { description: humanizeFlowError(err) });
    }
  };

  const handleDuplicate = async (card: FlowCardData) => {
    try {
      const copy = await cloneFlow(card.flow_id);
      toast.success(`Copied as "${copy.flow_name}"`, {
        description: copy.needs_setup.length > 0 ? `It is a draft. ${copy.needs_setup.map((n) => `${n.title}: ${n.what}`).join('. ')}` : 'It is a draft. Open it to make changes.',
        action: { label: 'Open', onClick: () => navigate(`/flows/${copy.flow_id}`) },
      });
      refresh();
    } catch (err) {
      toast.error('Could not copy the flow', { description: humanizeFlowError(err) });
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteFlow(deleteTarget.id);
      toast.success('Flow deleted');
      setDeleteTarget(null);
      refresh();
    } catch (err) {
      toast.error('Could not delete the flow', { description: humanizeFlowError(err) });
    } finally {
      setDeleting(false);
    }
  };

  const noFlowsAtAll = !loading && !failed && items.length === 0 && !isFiltered;

  return (
    <PageFrame
      title="Flows"
      badge={<ExperimentalBadge />}
      meta={!loading && total > 0 ? `${total} ${total === 1 ? 'flow' : 'flows'}` : undefined}
      actions={<FlowsListHeaderActions />}
      filters={
        <FlowListFilters
          search={search}
          onSearchChange={setSearch}
          status={status}
          onStatusChange={setStatus}
          statusOptions={STATUS_OPTIONS}
          category={category}
          onCategoryChange={setCategory}
          categoryOptions={categoryOptions}
          sort={sort}
          onSortChange={(v) => setSort(v as FlowListSort)}
          sortOptions={SORT_OPTIONS}
        />
      }
    >
      {failed && (
        <div className="py-12 text-center" data-testid="flow-list-error">
          <p className="mb-3 text-ui-text text-steel">The flows could not be loaded.</p>
          <Button variant="outline" onClick={refresh}>
            Try again
          </Button>
        </div>
      )}

      {!failed && (
        <GridView
          items={items}
          columns={{ sm: 1, md: 2, lg: 3 }}
          loading={loading}
          emptyState={
            noFlowsAtAll && canCreate ? (
              <FirstFlowCoach onStart={() => setShowNew(true)} />
            ) : noFlowsAtAll ? (
              <EmptyState
                variant="passive"
                icon={Workflow}
                title="No flows yet"
                description="No flows have been shared with you yet. Ask a teammate to share one, or ask your administrator for access to create flows."
                secondaryAction={{ label: 'How flows work', onClick: () => window.open(FLOW_GUIDE_URL, '_blank', 'noopener') }}
              />
            ) : (
              <EmptyState
                variant="no-results"
                icon={Workflow}
                title="No flows found"
                filterTerm={search}
                description={search.trim() ? `Nothing matches "${search.trim()}". Search looks in names, descriptions and categories.` : 'No flows match these filters.'}
                secondaryAction={{ label: 'Clear filters', onClick: clearFilters }}
              />
            )
          }
          renderItem={(card) => (
            <FlowCard
              card={card}
              canManage={canManage}
              canCreate={canCreate}
              onOpen={() => navigate(`/flows/${card.flow_id}`)}
              onRun={() => setRunTarget({ id: card.flow_id, name: card.flow_name })}
              onSettings={() => {
                // Stay on the list and open the shared settings dialog (read-only summary for view-only users).
                setActiveFlow(card.flow_id);
                setShowSettings(true);
              }}
              onDuplicate={() => void handleDuplicate(card)}
              onDelete={() => setDeleteTarget({ id: card.flow_id, name: card.flow_name, live: card.status === 'Active' })}
            />
          )}
          keyExtractor={(card) => card.flow_id}
        />
      )}

      {!failed && !loading && items.length > 0 && total > items.length && (
        <div className="flex flex-col items-center gap-1 pb-4" data-testid="flow-list-limit-note">
          <p className="text-xs text-steel">
            Showing {items.length} of {total} flows.
          </p>
          <LoadMoreButton hasMore loading={loadingMore} onLoadMore={() => void loadMore()} />
        </div>
      )}

      <RunFlowDialog
        open={!!runTarget}
        flowId={runTarget?.id ?? null}
        flowName={runTarget?.name}
        onOpenChange={(open) => !open && setRunTarget(null)}
        onRun={handleRun}
      />
      <FlowSettingsModal
        open={showSettings}
        onClose={() => {
          setShowSettings(false);
          // Refresh the list so name/description/category updates are visible without a manual reload.
          refresh();
        }}
      />
      <DeleteFlowDialog flow={deleteTarget} deleting={deleting} onCancel={() => setDeleteTarget(null)} onConfirm={() => void handleDelete()} />
      <NewFlowDialog open={showNew} onOpenChange={setShowNew} />
    </PageFrame>
  );
}
