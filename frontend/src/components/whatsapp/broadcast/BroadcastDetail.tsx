import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  cancelBroadcast, errorText, getBroadcast, listBroadcastRecipients, pauseBroadcast, resumeBroadcast,
  type Broadcast, type BroadcastRecipient, type WhatsAppResult,
} from '@/services/whatsappApi';
import { LoadError } from '../BridgeUnavailable';
import { COUNT_KEYS, isActive, POLL_MS, progressPercent } from './broadcastModel';

const STATUS_FILTERS = ['', ...COUNT_KEYS] as const;

export function BroadcastDetail({ name, onBack }: { name: string; onBack: () => void }) {
  const [b, setB] = useState<Broadcast | null>(null);
  const [rows, setRows] = useState<BroadcastRecipient[]>([]);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const filterRef = useRef(filter);
  filterRef.current = filter;

  const load = useCallback(async () => {
    const [bRes, rRes] = await Promise.all([
      getBroadcast(name),
      listBroadcastRecipients(name, { status: filterRef.current || undefined, limit: 100 }),
    ]);
    if (!bRes.success) { setError(errorText(bRes)); return; }
    setError('');
    setB(bRes.broadcast);
    if (rRes.success) setRows(rRes.recipients ?? []);
  }, [name]);

  useEffect(() => { void load(); }, [load, filter]);
  const active = b ? isActive(b.status) : false;
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(id);
  }, [active, load]);

  const act = async (fn: (n: string) => Promise<WhatsAppResult<unknown>>, done: string) => {
    setBusy(true);
    const res = await fn(name);
    setBusy(false);
    if (res.success) toast.success(done);
    else toast.error(errorText(res));
    await load();
  };

  if (error && !b) return <LoadError message={error} onRetry={load} />;
  if (!b) return <Skeleton className="h-40" />;
  const pct = progressPercent(b);

  return (
    <section aria-label={`Broadcast ${b.title || b.name}`} className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>Back to broadcasts</Button>
        <h2 className="text-base font-semibold text-ink">{b.title || b.name}</h2>
        <Badge variant="outline">{b.status}</Badge>
        {b.pause_reason ? <span className="text-xs text-steel">Paused: {b.pause_reason}</span> : null}
      </div>
      {error ? <LoadError message={error} onRetry={load} /> : null}

      <div>
        <Progress value={pct} aria-label="Broadcast progress" />
        <p className="mt-1 text-xs text-steel">{pct}% processed ({b.total} recipients)</p>
      </div>

      <dl className="grid grid-cols-3 gap-2 sm:grid-cols-5">
        {COUNT_KEYS.map((k) => (
          <div key={k} className="rounded-md border p-2">
            <dt className="text-xs capitalize text-steel">{k}</dt>
            <dd className="text-lg font-semibold text-ink" data-testid={`count-${k}`}>{b[k]}</dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-wrap gap-2">
        {b.status === 'Running' || b.status === 'Queued' ? (
          <Button variant="outline" disabled={busy} onClick={() => act(pauseBroadcast, 'Broadcast paused')}>Pause</Button>
        ) : null}
        {b.status === 'Paused' ? <Button disabled={busy} onClick={() => act(resumeBroadcast, 'Broadcast resumed')}>Resume</Button> : null}
        {['Running', 'Queued', 'Paused', 'Draft'].includes(b.status) ? (
          confirmCancel ? (
            <span className="flex items-center gap-2" role="group" aria-label="Confirm cancel">
              <span className="text-sm">Cancel this broadcast? Unsent messages will be skipped.</span>
              <Button variant="destructive" disabled={busy} onClick={() => { setConfirmCancel(false); void act(cancelBroadcast, 'Broadcast cancelled'); }}>Yes, cancel broadcast</Button>
              <Button variant="ghost" onClick={() => setConfirmCancel(false)}>Keep</Button>
            </span>
          ) : (
            <Button variant="outline" disabled={busy} onClick={() => setConfirmCancel(true)}>Cancel broadcast</Button>
          )
        ) : null}
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="broadcast-status-filter" className="text-sm text-steel">Status</label>
        <select
          id="broadcast-status-filter"
          className="h-9 rounded-md border bg-background px-2 text-sm"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          {STATUS_FILTERS.map((s) => <option key={s} value={s}>{s || 'All'}</option>)}
        </select>
      </div>
      <Table aria-label="Recipients">
        <TableHeader>
          <TableRow><TableHead>Recipient</TableHead><TableHead>Status</TableHead><TableHead>Error code</TableHead><TableHead>Detail</TableHead></TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow><TableCell colSpan={4} className="text-center text-steel">No recipients</TableCell></TableRow>
          ) : rows.map((r) => (
            <TableRow key={r.name}>
              <TableCell>{r.recipient}</TableCell>
              <TableCell>{r.status}</TableCell>
              <TableCell>{r.error_code ?? ''}</TableCell>
              <TableCell>{r.error_message || r.skip_reason || ''}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}
