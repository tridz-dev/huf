import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Field } from '@/components/ui/field';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { errorText, type WhatsAppResult } from '@/services/whatsappApi';
import { cancelBroadcast, deleteBroadcast, getBroadcast, listBroadcastRecipients, pauseBroadcast, removeBroadcastRecipient, resumeBroadcast, retryFailedRecipients, unscheduleBroadcast, type Broadcast, type BroadcastRecipient } from './broadcastApi';
import { LoadError } from '../BridgeUnavailable';
import { COUNT_KEYS, isActive, POLL_MS, progressPercent } from './broadcastModel';
import { useBroadcastRealtime, type BroadcastProgress } from './useBroadcastRealtime';

const RECONCILE_MS = 30000;

const PAGE = 100;
const ALL = 'all';
const STATUS_FILTERS = ['', ...COUNT_KEYS] as const;

export function BroadcastDetail({ name, onBack }: { name: string; onBack: () => void }) {
  const [b, setB] = useState<Broadcast | null>(null);
  const [rows, setRows] = useState<BroadcastRecipient[]>([]);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const limitRef = useRef(limit);
  limitRef.current = limit;
  const filterRef = useRef(filter);
  filterRef.current = filter;

  const load = useCallback(async () => {
    const [bRes, rRes] = await Promise.all([
      getBroadcast(name),
      listBroadcastRecipients(name, { status: filterRef.current || undefined, limit: limitRef.current }),
    ]);
    if (!bRes.success) { setError(errorText(bRes)); return; }
    setError('');
    setB(bRes.broadcast);
    if (rRes.success) setRows(rRes.recipients ?? []);
  }, [name]);

  useEffect(() => { void load(); }, [load, filter, limit]);
  const active = b ? isActive(b.status) : false;
  const rowsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onProgress = useCallback((p: BroadcastProgress) => {
    setB((prev) => (prev && prev.name === p.broadcast ? { ...prev, ...p, name: prev.name } as Broadcast : prev));
    // counters come with the event; the recipient table is re-read shortly after (at most every 2s)
    if (!rowsTimer.current) rowsTimer.current = setTimeout(() => { rowsTimer.current = null; void load(); }, 2000);
  }, [load]);
  useEffect(() => () => { if (rowsTimer.current) clearTimeout(rowsTimer.current); }, []);
  const { live } = useBroadcastRealtime(name, onProgress);
  // Polling stays as the fallback: every 5s without the socket, a 30s reconcile while it is live.
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => void load(), live ? RECONCILE_MS : POLL_MS);
    return () => clearInterval(id);
  }, [active, live, load]);

  const act = async (fn: (n: string) => Promise<WhatsAppResult<unknown>>, done: string) => {
    setBusy(true);
    const res = await fn(name);
    setBusy(false);
    if (res.success) toast.success(done);
    else toast.error(errorText(res));
    await load();
  };

  const retry = async () => {
    setBusy(true);
    const res = await retryFailedRecipients(name);
    setBusy(false);
    if (res.success) toast.success(`Created a draft with ${res.added ?? 0} recipients to retry: ${res.broadcast ?? ''}`);
    else toast.error(errorText(res));
  };

  const remove = async (r: BroadcastRecipient) => {
    setBusy(true);
    const res = await removeBroadcastRecipient(name, r.recipient);
    setBusy(false);
    if (res.success) toast.success('Recipient removed');
    else toast.error(errorText(res));
    await load();
  };

  const discard = async () => {
    setBusy(true);
    const res = await deleteBroadcast(name);
    setBusy(false);
    if (res.success) { toast.success('Draft deleted'); onBack(); }
    else toast.error(errorText(res));
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
        {b.send_via === 'marketing_messages' ? <Badge variant="secondary">Marketing Messages API</Badge> : <Badge variant="outline">Cloud API</Badge>}
        {b.pause_reason ? <span className="text-xs text-steel">Paused: {b.pause_reason}</span> : null}
        {active ? (
          <span className="ml-auto flex items-center gap-1 text-xs text-steel" role="status" aria-label={live ? 'Live updates' : 'Updating by polling'}>
            <span aria-hidden className={`inline-block size-2 rounded-full ${live ? 'bg-good' : 'bg-muted-foreground'}`} />
            {live ? 'Live' : 'Polling'}
          </span>
        ) : null}
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
        {b.status === 'Scheduled' ? (
          <>
            <span className="self-center text-sm text-ink">Scheduled for {b.scheduled_at ?? ''} (site time)</span>
            <Button variant="outline" disabled={busy} onClick={() => act(unscheduleBroadcast, 'Broadcast unscheduled')}>Unschedule</Button>
          </>
        ) : null}
        {b.failed > 0 && ['Completed', 'Cancelled', 'Paused', 'Failed'].includes(b.status) ? (
          <Button variant="outline" disabled={busy} onClick={() => void retry()}>Retry failed ({b.failed})</Button>
        ) : null}
        {['Running', 'Queued', 'Paused', 'Draft', 'Scheduled'].includes(b.status) ? (
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

      {b.status === 'Draft' ? (
        <div className="flex flex-wrap items-center gap-2">
          {confirmDelete ? (
            <span className="flex items-center gap-2" role="group" aria-label="Confirm delete">
              <span className="text-sm">Delete this draft and its recipient list?</span>
              <Button variant="destructive" disabled={busy} onClick={() => void discard()}>Yes, delete draft</Button>
              <Button variant="ghost" onClick={() => setConfirmDelete(false)}>Keep</Button>
            </span>
          ) : (
            <Button variant="outline" disabled={busy} onClick={() => setConfirmDelete(true)}>Delete draft</Button>
          )}
          <p className="text-xs text-steel">A draft has not sent anything. Remove people from the list below, or delete the draft.</p>
        </div>
      ) : null}

      <Field label="Status" id="broadcast-status-filter" className="max-w-48">
        {(p) => (
          <Select value={filter || ALL} onValueChange={(v) => setFilter(v === ALL ? '' : v)}>
            <SelectTrigger {...p} aria-label="Status"><SelectValue /></SelectTrigger>
            <SelectContent>
              {STATUS_FILTERS.map((st) => <SelectItem key={st || ALL} value={st || ALL}>{st || 'All'}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
      </Field>
      <Table aria-label="Recipients">
        <TableHeader>
          <TableRow><TableHead>Recipient</TableHead><TableHead>Status</TableHead><TableHead>Error code</TableHead><TableHead>Detail</TableHead>{b.status === 'Draft' ? <TableHead><span className="sr-only">Actions</span></TableHead> : null}</TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow><TableCell colSpan={b.status === 'Draft' ? 5 : 4} className="text-center text-steel">No recipients</TableCell></TableRow>
          ) : rows.map((r) => (
            <TableRow key={r.name}>
              <TableCell>{r.recipient}</TableCell>
              <TableCell>{r.status}</TableCell>
              <TableCell>{r.error_code ?? ''}</TableCell>
              <TableCell>{r.error_message || r.skip_reason || ''}</TableCell>
              {b.status === 'Draft' ? (
                <TableCell className="text-right">
                  <Button variant="ghost" size="sm" disabled={busy} aria-label={`Remove ${r.recipient}`} onClick={() => void remove(r)}>Remove</Button>
                </TableCell>
              ) : null}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {rows.length >= limit ? (
        <Button variant="outline" onClick={() => setLimit((n) => n + PAGE)}>Show more</Button>
      ) : null}
    </section>
  );
}
