import { useEffect, useMemo, useState } from 'react';
import { BookOpen } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, GridView, LoadMoreButton, EmptyState } from '../components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { deleteKnowledgeSource, getKnowledgeSources, updateKnowledgeSource } from '../services/knowledgeApi';
import { getFrappeErrorMessage } from '../lib/frappe-error';
import { CreateSourceDialog } from '../components/knowledge/CreateSourceDialog';
import { ConfirmActionDialog } from '../components/knowledge/import/ConfirmActionDialog';
import { AddContentDialog } from '../components/knowledge/import/AddContentDialog';
import { SourceCard } from '../components/knowledge/library/SourceCard';
import { LibraryEmptyState } from '../components/knowledge/library/LibraryEmptyState';
import { RenameSourceDialog } from '../components/knowledge/library/RenameSourceDialog';
import { useLibraryStats } from '../components/knowledge/library/useLibraryStats';
import { Input } from '@/components/ui/input';
import { HEALTH_LABEL, computeHealth, type SourceHealth } from '../components/agent/knowledge/sourceHealth';
import type { KnowledgeSourceDoc } from '../types/knowledge.types';

const HEALTH_FILTERS = [
  { label: 'All status', value: 'all' },
  ...(Object.keys(HEALTH_LABEL) as SourceHealth[]).map((k) => ({ label: HEALTH_LABEL[k], value: k })),
];

export { KnowledgeSourcesPage };
export default KnowledgeSourcesPage;

function KnowledgeSourcesPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const createOpen = searchParams.get('new') === '1';
  const openCreate = () =>
    setSearchParams((p) => {
      const n = new URLSearchParams(p);
      n.set('new', '1');
      return n;
    });
  const setCreateOpen = (o: boolean) => {
    if (o) return openCreate();
    setSearchParams((p) => {
      const n = new URLSearchParams(p);
      n.delete('new');
      n.delete('agent');
      return n;
    }, { replace: true });
  };
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeSourceDoc | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [typedName, setTypedName] = useState('');
  const [addTarget, setAddTarget] = useState<KnowledgeSourceDoc | null>(null);
  const [renameTarget, setRenameTarget] = useState<KnowledgeSourceDoc | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [healthFilter, setHealthFilter] = useState('all');
  const [statsKey, setStatsKey] = useState(0);

  const {
    items: sources,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    reset,
    total,
    error,
  } = useInfiniteScroll<
    { status?: string; page?: number; limit?: number; start?: number; search?: string },
    KnowledgeSourceDoc
  >({
    fetchFn: async (params) => {
      const response = await getKnowledgeSources({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: params.status,
      });

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

  const { countsFor, agentsFor } = useLibraryStats(`${statsKey}:${sources.length}`);
  const visible = useMemo(
    () => (healthFilter === 'all' ? sources : sources.filter((x) => computeHealth(x, countsFor(x.name)) === healthFilter)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sources, healthFilter, statsKey, countsFor],
  );
  const filtered = !!search || healthFilter !== 'all';

  const toggleDisabled = async (src: KnowledgeSourceDoc) => {
    try {
      await updateKnowledgeSource(src.name, { disabled: src.disabled ? 0 : 1 });
      toast.success(src.disabled ? 'Turned on' : 'Turned off');
      await reset();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e) || 'Could not update this knowledge source');
    }
  };

  useEffect(() => {
    if (error) {
      toast.error('Failed to load knowledge sources', {
        description: error.message || 'An error occurred while fetching knowledge sources.',
        duration: 5000,
      });
    }
  }, [error]);

  return (
    <PageFrame
      filters={
        <FilterBar
          searchPlaceholder="Search knowledge sources..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Status',
              value: healthFilter,
              options: HEALTH_FILTERS,
              onChange: (value: string) => setHealthFilter(value),
            },
          ]}
        />
      }
    >
      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load knowledge sources</p>
          <p className="text-sm text-steel mb-4">
            {error.message || 'An error occurred while fetching knowledge sources.'}
          </p>
        </div>
      )}
      <GridView
        items={visible}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          filtered ? (
            <EmptyState
              variant="no-results"
              icon={BookOpen}
              title="No knowledge sources found"
              filterTerm={search}
              secondaryAction={{
                label: 'Clear filters',
                onClick: () => {
                  setSearch('');
                  setHealthFilter('all');
                },
              }}
            />
          ) : (
            <LibraryEmptyState onUpload={openCreate} onConnect={openCreate} />
          )
        }
        renderItem={(source) => (
          <SourceCard
            source={source}
            counts={countsFor(source.name)}
            agentCount={agentsFor(source.name)}
            onOpen={() => navigate(`/knowledge/${source.name}`)}
            onTest={() => navigate(`/knowledge/${source.name}#test`)}
            onAddFiles={() => setAddTarget(source)}
            onRename={() => setRenameTarget(source)}
            onToggleDisabled={() => void toggleDisabled(source)}
            onDelete={() => {
              setTypedName('');
              setDeleteTarget(source);
            }}
          />
        )}
        keyExtractor={(source) => source.name}
      />
      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />
      {!hasMore && sources.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined
            ? `Showing all ${total} knowledge sources`
            : 'No more knowledge sources to load'}
        </div>
      )}
      <CreateSourceDialog open={createOpen} onOpenChange={setCreateOpen} agent={searchParams.get('agent')} />
      <ConfirmActionDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title={`Delete "${deleteTarget?.source_name || deleteTarget?.name}"?`}
        description={
          <>
            This removes the source and all of its documents. Agents using it will lose access. This cannot be undone.
            {deleteTarget && countsFor(deleteTarget.name).total > 0 && (
              <Input
                className="mt-3"
                placeholder={`Type "${deleteTarget.source_name || deleteTarget.name}" to confirm`}
                value={typedName}
                onChange={(e) => setTypedName(e.target.value)}
              />
            )}
          </>
        }
        confirmDisabled={
          !!deleteTarget &&
          countsFor(deleteTarget.name).total > 0 &&
          typedName.trim() !== (deleteTarget.source_name || deleteTarget.name)
        }
        confirmLabel="Delete source"
        destructive
        busy={deleting}
        onConfirm={async () => {
          if (!deleteTarget) return;
          setDeleting(true);
          try {
            await deleteKnowledgeSource(deleteTarget.name);
            toast.success('Knowledge source deleted');
            setDeleteTarget(null);
            await reset();
          } catch (e) {
            toast.error(getFrappeErrorMessage(e) || 'Could not delete this knowledge source');
          } finally {
            setDeleting(false);
          }
        }}
      />
      {addTarget && (
        <AddContentDialog
          open
          onOpenChange={(o) => !o && setAddTarget(null)}
          knowledgeSource={addTarget.name}
          sourceLabel={addTarget.source_name || addTarget.name}
          onStarted={() => {
            const n = addTarget.name;
            setAddTarget(null);
            navigate(`/knowledge/${n}`);
          }}
          onInputAdded={() => {
            setAddTarget(null);
            setStatsKey((k) => k + 1);
          }}
        />
      )}
      <RenameSourceDialog
        open={renameTarget !== null}
        initial={renameTarget?.source_name || renameTarget?.name || ''}
        busy={renaming}
        onOpenChange={(o) => !o && setRenameTarget(null)}
        onSave={async (name) => {
          if (!renameTarget) return;
          setRenaming(true);
          try {
            await updateKnowledgeSource(renameTarget.name, { source_name: name });
            setRenameTarget(null);
            await reset();
          } catch (e) {
            toast.error(getFrappeErrorMessage(e) || 'Could not rename this knowledge source');
          } finally {
            setRenaming(false);
          }
        }}
      />
    </PageFrame>
  );
}
