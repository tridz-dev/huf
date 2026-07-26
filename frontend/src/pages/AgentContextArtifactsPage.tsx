import { useMemo } from 'react';
import { Loader2 } from 'lucide-react';
import { FilterBar, PageLayout, LoadMoreButton } from '@/components/dashboard';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getArtifacts, type AgentContextArtifactDoc, type ArtifactListParams } from '@/services/agentContextArtifactApi';
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

export { AgentContextArtifactsPage };
export default AgentContextArtifactsPage;

const ARTIFACT_TYPE_OPTIONS = [
  { label: 'All Types', value: 'all' },
  { label: 'JSON', value: 'JSON' },
  { label: 'File', value: 'File' },
  { label: 'Text', value: 'Text' },
];

const VISIBILITY_OPTIONS = [
  { label: 'All Visibility', value: 'all' },
  { label: 'User Visible', value: 'user_visible' },
  { label: 'Model Visible', value: 'model_visible' },
  { label: 'UI Only', value: 'ui_only' },
  { label: 'Audit Only', value: 'audit_only' },
  { label: 'Developer Only', value: 'developer_only' },
];

function AgentContextArtifactsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const {
    items: artifacts,
    hasMore,
    initialLoading,
    loadingMore,
    loadMore,
    total,
    filters,
    setFilter,
  } = useInfiniteScroll<ArtifactListParams, AgentContextArtifactDoc>({
    fetchFn: (params) => getArtifacts(params),
    initialParams: {
      artifact_type: searchParams.get('type') || 'all',
      visibility: searchParams.get('visibility') || 'all',
    },
    pageSize: 20,
    autoLoad: true,
  });

  const updateSearchParams = (next: { type?: string; visibility?: string }) => {
    setSearchParams((prev) => {
      const sp = new URLSearchParams(prev);
      if (next.type !== undefined) {
        if (next.type && next.type !== 'all') sp.set('type', next.type);
        else sp.delete('type');
      }
      if (next.visibility !== undefined) {
        if (next.visibility && next.visibility !== 'all') sp.set('visibility', next.visibility);
        else sp.delete('visibility');
      }
      return sp;
    });
  };

  const columns = useMemo(
    () => [
      { key: 'summary', header: 'Summary' },
      { key: 'artifact_type', header: 'Type' },
      { key: 'agent_run', header: 'Agent Run' },
      { key: 'visibility', header: 'Visibility' },
      { key: 'created', header: 'Created' },
    ],
    []
  );

  return (
    <PageLayout
      subtitle="Browse context artifacts stored for agent runs and conversations"
      filters={
        <FilterBar
          filters={[
            {
              label: 'Type',
              value: filters.artifact_type || 'all',
              options: ARTIFACT_TYPE_OPTIONS,
              onChange: (value) => {
                setFilter('artifact_type', value);
                updateSearchParams({ type: value });
              },
            },
            {
              label: 'Visibility',
              value: filters.visibility || 'all',
              options: VISIBILITY_OPTIONS,
              onChange: (value) => {
                setFilter('visibility', value);
                updateSearchParams({ visibility: value });
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
        ) : (
          <div className="overflow-hidden rounded-none border">
            <Table>
              <TableHeader>
                <TableRow>
                  {columns.map((col) => (
                    <TableHead key={col.key}>{col.header}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {artifacts.length ? (
                  artifacts.map((artifact) => (
                    <TableRow
                      key={artifact.name}
                      className="cursor-pointer hover:bg-paper-deep"
                      onClick={() => navigate(`/artifacts/${artifact.name}`)}
                    >
                      <TableCell className="max-w-md truncate">
                        {artifact.summary || <span className="font-body text-steel">No summary</span>}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{artifact.artifact_type || 'Unknown'}</Badge>
                      </TableCell>
                      <TableCell className="font-mono text-sm text-steel-soft">
                        {artifact.agent_run || '—'}
                      </TableCell>
                      <TableCell className="text-sm">{artifact.visibility || '—'}</TableCell>
                      <TableCell className="text-sm text-steel">
                        {formatTimeAgo(artifact.creation ?? null)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={columns.length} className="h-24 text-center">
                      <div className="font-body text-steel-soft">No artifacts found.</div>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <LoadMoreButton hasMore={hasMore} loading={loadingMore} onLoadMore={loadMore} disabled={initialLoading} />

      {!hasMore && artifacts.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} artifacts` : 'No more artifacts to load'}
        </div>
      )}
    </PageLayout>
  );
}
