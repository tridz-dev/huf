import { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { listEntryPoints } from '@/services/solutionsApi';
import type { EntryPoint, SolutionOverview } from '@/types/solutions';
import { EntryPointSheet, describeRule, type Ceiling } from './EntryPointSheet';

interface EntryPointsTabProps {
  overview: SolutionOverview;
  /** Bump to reload from outside. */
  refreshKey?: number;
  onChanged?: () => void;
  /** Reports loaded entries (used for test chat chips). */
  onLoaded?: (entries: EntryPoint[]) => void;
}

export function EntryPointsTab({ overview, refreshKey = 0, onChanged, onLoaded }: EntryPointsTabProps) {
  const [entries, setEntries] = useState<EntryPoint[] | null>(null);
  const [error, setError] = useState('');
  const [sheet, setSheet] = useState<{ open: boolean; entry: EntryPoint | null }>({ open: false, entry: null });

  const load = useCallback(async () => {
    setError('');
    try {
      const list = await listEntryPoints(overview.name);
      setEntries(list);
      onLoaded?.(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load entry points.');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overview.name]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const gateways = overview.runs_on;
  const labelOf = (g: string) => gateways.find((r) => r.gateway === g)?.label ?? g;

  const ceilingFor = useCallback(
    (gateway: string): Ceiling => {
      const hit = entries?.find((e) => e.gateway === gateway);
      if (hit) return { value: hit.ceiling, source: hit.ceiling_source };
      return overview.cost.ceiling !== null ? { value: overview.cost.ceiling, source: 'gateway_cap' } : { value: null, source: 'none' };
    },
    [entries, overview.cost.ceiling],
  );

  const grouped = useMemo(() => {
    const map = new Map<string, EntryPoint[]>();
    for (const g of gateways) map.set(g.gateway, []);
    for (const e of [...(entries ?? [])].sort((a, b) => a.priority - b.priority)) {
      map.set(e.gateway, [...(map.get(e.gateway) ?? []), e]);
    }
    return [...map.entries()];
  }, [entries, gateways]);

  const done = () => {
    void load();
    onChanged?.();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-steel">The rules that send a customer message to {overview.title}, in the order they are checked.</p>
        <Button size="sm" onClick={() => setSheet({ open: true, entry: null })} disabled={gateways.length === 0}>
          <Plus className="mr-1 h-3.5 w-3.5" aria-hidden />
          Add entry point
        </Button>
      </div>

      {error ? (
        <div role="alert" className="flex items-center gap-3 text-sm">
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={() => void load()}>Retry</Button>
        </div>
      ) : entries === null ? (
        <Skeleton className="h-32" />
      ) : (
        grouped.map(([gateway, rows]) => (
          <section key={gateway} aria-label={`Entry points on ${labelOf(gateway)}`} className="space-y-2">
            <h3 className="text-sm font-semibold text-ink">{labelOf(gateway)}</h3>
            {rows.length === 0 ? (
              <p className="text-sm text-steel">No entry points on this number yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">Order</TableHead>
                    <TableHead>Rule</TableHead>
                    <TableHead className="w-28">Cap / day</TableHead>
                    <TableHead className="w-20" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((e, i) => (
                    <TableRow key={e.name} className="cursor-pointer" onClick={() => setSheet({ open: true, entry: e })}>
                      <TableCell>{i + 1}</TableCell>
                      <TableCell>
                        {describeRule(e)}
                        {e.target_type === 'Triage' ? <Badge variant="outline" className="ml-2">Menu</Badge> : null}
                      </TableCell>
                      <TableCell>{e.cap_per_day ?? '-'}</TableCell>
                      <TableCell>
                        <Button variant="ghost" size="sm" onClick={(ev) => { ev.stopPropagation(); setSheet({ open: true, entry: e }); }}>
                          Edit
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>
        ))
      )}

      <EntryPointSheet
        open={sheet.open}
        onOpenChange={(open) => setSheet((s) => ({ ...s, open }))}
        solution={overview.name}
        entry={sheet.entry}
        gateways={gateways}
        gatewayScope={overview.limits.scope}
        ceilingFor={ceilingFor}
        onSaved={done}
      />
    </div>
  );
}
