import { useCallback, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { listSolutionConversations } from '@/services/solutionsApi';
import type { SolutionConversation, SolutionOverview } from '@/types/solutions';

interface Props {
  overview: SolutionOverview;
  solutionLabels?: Record<string, string>;
}

const nativeSelect =
  'h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

function when(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
}

export function SolutionConversationsTab({ overview, solutionLabels = {} }: Props) {
  const [scope, setScope] = useState<'all' | 'only'>('only');
  const [rows, setRows] = useState<SolutionConversation[] | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setRows(null);
    setError('');
    try {
      setRows(await listSolutionConversations(scope === 'all' ? null : overview.name));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load conversations.');
    }
  }, [scope, overview.name]);

  useEffect(() => {
    void load();
  }, [load]);

  const numberOf = (g: string) => overview.runs_on.find((r) => r.gateway === g)?.label ?? g;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <label htmlFor="convs-scope" className="text-sm text-steel">Show</label>
        <select id="convs-scope" className={nativeSelect} value={scope} onChange={(e) => setScope(e.target.value as 'all' | 'only')}>
          <option value="all">All inboxes</option>
          <option value="only">Only {overview.title}</option>
        </select>
      </div>
      {error ? (
        <div role="alert" className="flex items-center gap-3 text-sm">
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={() => void load()}>Retry</Button>
        </div>
      ) : rows === null ? (
        <Skeleton className="h-32" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-steel">No conversations yet.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Contact</TableHead>
              <TableHead>Latest message</TableHead>
              <TableHead>Solution</TableHead>
              <TableHead>Number</TableHead>
              <TableHead>Time</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={`${r.gateway}-${r.contact}-${i}`}>
                <TableCell className="font-medium">{r.contact}</TableCell>
                <TableCell className="max-w-xs truncate text-steel">{r.preview}</TableCell>
                <TableCell>
                  {r.solution ? <Badge variant="outline">{solutionLabels[r.solution] ?? (r.solution === overview.name ? overview.title : r.solution)}</Badge> : <span className="text-steel">-</span>}
                </TableCell>
                <TableCell>{numberOf(r.gateway)}</TableCell>
                <TableCell className="whitespace-nowrap text-steel">{when(r.ts)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
