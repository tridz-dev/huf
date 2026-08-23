import { useMemo } from 'react';
import { ListTree, Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import {
  getAgentProcedures,
  getSourceFlowId,
  type AgentProcedureDoc,
  type AgentProcedureListParams,
} from '@/services/agentProcedureApi';
import { formatTimeAgo } from '@/utils/time';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

export { AgentProceduresPage };
export default AgentProceduresPage;

const STATUS_OPTIONS = [
  { label: 'All Status', value: 'all' },
  { label: 'Draft', value: 'Draft' },
  { label: 'Testing', value: 'Testing' },
  { label: 'Active', value: 'Active' },
  { label: 'Disabled', value: 'Disabled' },
  { label: 'Archived', value: 'Archived' },
];

const TIER_OPTIONS = [
  { label: 'All Tiers', value: 'all' },
  { label: 'Draft', value: 'Draft' },
  { label: 'Compiled', value: 'Compiled' },
  { label: 'System', value: 'System' },
];

function tierVariant(tier?: string): 'default' | 'secondary' | 'outline' {
  if (tier === 'System') return 'default';
  if (tier === 'Compiled') return 'secondary';
  return 'outline';
}

function AgentProceduresPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const {
    items: procedures,
    hasMore,
    initialLoading,
    loadingMore,
    loadMore,
    total,
    filters,
    setFilter,
  } = useInfiniteScroll<AgentProcedureListParams, AgentProcedureDoc>({
    fetchFn: (params) => getAgentProcedures(params),
    initialParams: {
      status: searchParams.get('status') || 'all',
      tier: searchParams.get('tier') || 'all',
    },
    pageSize: 20,
    autoLoad: true,
  });

  const updateSearchParams = (next: { status?: string; tier?: string }) => {
    setSearchParams((prev) => {
      const sp = new URLSearchParams(prev);
      if (next.status !== undefined) {
        if (next.status && next.status !== 'all') sp.set('status', next.status);
        else sp.delete('status');
      }
      if (next.tier !== undefined) {
        if (next.tier && next.tier !== 'all') sp.set('tier', next.tier);
        else sp.delete('tier');
      }
      return sp;
    });
  };

  const columns = useMemo(
    () => [
      { key: 'procedure_name', header: 'Name' },
      { key: 'tier', header: 'Tier' },
      { key: 'status', header: 'Status' },
      { key: 'version', header: 'Version' },
      { key: 'source_flow', header: 'Source Flow' },
      { key: 'modified', header: 'Updated' },
    ],
    []
  );

  return (
    <PageFrame
      title="Procedures"
      filters={
        <FilterBar
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: STATUS_OPTIONS,
              onChange: (value) => {
                setFilter('status', value);
                updateSearchParams({ status: value });
              },
            },
            {
              label: 'Tier',
              value: filters.tier || 'all',
              options: TIER_OPTIONS,
              onChange: (value) => {
                setFilter('tier', value);
                updateSearchParams({ tier: value });
              },
            },
          ]}
        />
      }
    >
      <div className="w-full">
        {initialLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : procedures.length === 0 ? (
          <EmptyState
            icon={ListTree}
            title="No procedures"
            description="No Agent Procedures have been created yet."
          />
        ) : (
          <div className="border border-line bg-panel">
            <Table>
              <TableHeader>
                <TableRow>
                  {columns.map((col) => (
                    <TableHead key={col.key}>{col.header}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {procedures.map((procedure) => {
                  const sourceFlowId = getSourceFlowId(procedure);
                  return (
                    <TableRow
                      key={procedure.name}
                      className="cursor-pointer hover:bg-paper-deep"
                      onClick={() => navigate(`/procedures/${procedure.name}`)}
                    >
                      <TableCell className="max-w-md truncate">
                        {procedure.procedure_name || procedure.name}
                      </TableCell>
                      <TableCell>
                        <Badge variant={tierVariant(procedure.tier)}>{procedure.tier || 'Draft'}</Badge>
                      </TableCell>
                      <TableCell className="text-sm">{procedure.status || '—'}</TableCell>
                      <TableCell className="text-sm">{procedure.version ?? '—'}</TableCell>
                      <TableCell className="font-mono text-sm text-steel-soft">
                        {sourceFlowId ? (
                          <span
                            className="hover:underline"
                            onClick={(event) => {
                              event.stopPropagation();
                              navigate(`/flows/${sourceFlowId}`);
                            }}
                          >
                            {sourceFlowId}
                          </span>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-steel">
                        {formatTimeAgo(procedure.modified ?? procedure.creation ?? null)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <LoadMoreButton hasMore={hasMore} loading={loadingMore} onLoadMore={loadMore} disabled={initialLoading} />

      {!hasMore && procedures.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} procedures` : 'No more procedures to load'}
        </div>
      )}
    </PageFrame>
  );
}
