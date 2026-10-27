import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { errorText } from '@/services/whatsappApi';
import { listBroadcasts, type Broadcast } from './broadcastApi';
import { LoadError } from '../BridgeUnavailable';

export function BroadcastList({ gateway, onOpen, onNew, refreshKey = 0 }: {
  gateway: string; onOpen: (name: string) => void; onNew: () => void; refreshKey?: number;
}) {
  const [items, setItems] = useState<Broadcast[] | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    const res = await listBroadcasts({ gateway, limit: 50 });
    if (res.success) setItems(res.broadcasts ?? []);
    else setError(errorText(res));
  }, [gateway]);
  useEffect(() => { setItems(null); void load(); }, [load, refreshKey]);

  return (
    <section aria-label="Broadcasts" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Broadcasts</h2>
        <Button onClick={onNew}>New broadcast</Button>
      </div>
      {error ? (
        <LoadError message={error} onRetry={load} />
      ) : !items ? (
        <Skeleton className="h-24" />
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-sm text-steel">No broadcasts yet. Create one to message many contacts with an approved template.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead><TableHead>Status</TableHead><TableHead>Template</TableHead>
              <TableHead className="text-right">Recipients</TableHead><TableHead className="text-right">Sent</TableHead><TableHead className="text-right">Failed</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((b) => (
              <TableRow key={b.name}>
                <TableCell>
                  <Button variant="link" className="h-auto p-0" onClick={() => onOpen(b.name)} aria-label={`Open broadcast ${b.title || b.name}`}>{b.title || b.name}</Button>
                </TableCell>
                <TableCell><Badge variant="outline">{b.status}</Badge></TableCell>
                <TableCell>{b.template_name ?? b.template}</TableCell>
                <TableCell className="text-right">{b.total}</TableCell>
                <TableCell className="text-right">{b.sent + b.delivered + b.read}</TableCell>
                <TableCell className="text-right">{b.failed}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}
