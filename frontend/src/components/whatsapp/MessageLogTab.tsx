import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useDebounce } from '@/hooks/useDebounce';
import {
  errorText, listMessageLog, listMessageLogFilters,
  type MessageLogFilterOptions, type MessageLogItem,
} from '@/services/whatsappApi';
import { BridgeUnavailable, LoadError } from './BridgeUnavailable';
import { MessageDetailSheet, StatusTicks } from './MessageDetailSheet';
import { SendPanel } from './SendPanel';
import {
  ALL, EMPTY_FILTERS, activeFilterCount, agentRunPath, filtersFromParams, filtersToParams, filtersToQuery,
  messagePreview, sentByLabel, type MessageLogFilters,
} from './messageLogModel';

function FilterSelect({
  label, value, onChange, options,
}: { label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? '' : v)}>
      <SelectTrigger className="w-40" aria-label={label}><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{`All ${label.toLowerCase()}s`}</SelectItem>
        {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

export function MessageLogTab({ gateway, bridgeAvailable }: { gateway?: string; bridgeAvailable: boolean }) {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => filtersFromParams(params), [params]);
  const [options, setOptions] = useState<MessageLogFilterOptions | null>(null);
  const [items, setItems] = useState<MessageLogItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<MessageLogItem | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const requestId = useRef(0);

  // Text inputs stay local while typing and reach the URL (and the query) after a short pause.
  const [qInput, setQInput] = useState(filters.q);
  const [phoneInput, setPhoneInput] = useState(filters.phone);
  const debouncedQ = useDebounce(qInput, 400);
  const debouncedPhone = useDebounce(phoneInput, 400);

  const update = useCallback((patch: Partial<MessageLogFilters>) => {
    setParams((prev) => filtersToParams({ ...filtersFromParams(prev), ...patch }, prev), { replace: true });
  }, [setParams]);

  useEffect(() => {
    if (qInput === debouncedQ && debouncedQ !== filters.q) update({ q: debouncedQ });
  }, [qInput, debouncedQ, filters.q, update]);
  useEffect(() => {
    if (phoneInput === debouncedPhone && debouncedPhone !== filters.phone) update({ phone: debouncedPhone });
  }, [phoneInput, debouncedPhone, filters.phone, update]);

  useEffect(() => {
    if (!gateway) return;
    let live = true;
    void listMessageLogFilters(gateway).then((res) => { if (live && res.success) setOptions(res); });
    return () => { live = false; };
  }, [gateway]);

  const query = useMemo(() => filtersToQuery(filters), [filters]);

  useEffect(() => {
    if (!gateway) { setItems([]); setLoading(false); return; }
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    void listMessageLog(gateway, query).then((res) => {
      if (id !== requestId.current) return;
      if (res.success) { setItems(res.items); setCursor(res.next_cursor); setHasMore(res.has_more); } else setError(errorText(res));
      setLoading(false);
    });
  }, [gateway, query, reloadKey]);

  const loadMore = async () => {
    if (!gateway || !cursor) return;
    const id = requestId.current;
    setLoadingMore(true);
    const res = await listMessageLog(gateway, { ...query, cursor });
    if (id !== requestId.current) return;
    setLoadingMore(false);
    if (res.success) { setItems((prev) => [...prev, ...res.items]); setCursor(res.next_cursor); setHasMore(res.has_more); } else setError(errorText(res));
  };

  const reset = () => {
    setQInput(''); setPhoneInput('');
    setParams((prev) => filtersToParams(EMPTY_FILTERS, prev), { replace: true });
  };

  const agentTitle = (name: string | null) => options?.agents.find((a) => a.name === name)?.title;
  const active = activeFilterCount(filters);
  const opt = (values: string[] | undefined) => (values ?? []).map((v) => ({ value: v, label: cap(v) }));

  return (
    <div className="space-y-3">
      <SendPanel gateway={gateway} onSent={() => setReloadKey((k) => k + 1)} />

      {!bridgeAvailable && (
        <p role="status" className="rounded-sm border border-line bg-paper-deep px-3 py-2 text-xs text-steel">
          This log shows gateway events only. Message history from the WhatsApp Business app connector is unavailable.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Input value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Search messages" className="w-56" aria-label="Search messages" />
        <FilterSelect label="Direction" value={filters.direction} onChange={(v) => update({ direction: v as MessageLogFilters['direction'] })}
          options={[{ value: 'in', label: 'In' }, { value: 'out', label: 'Out' }]} />
        <FilterSelect label="Status" value={filters.status} onChange={(v) => update({ status: v })} options={opt(options?.statuses)} />
        <FilterSelect label="Agent" value={filters.agent} onChange={(v) => update({ agent: v })}
          options={(options?.agents ?? []).map((a) => ({ value: a.name, label: a.title || a.name }))} />
        <FilterSelect label="Template" value={filters.template} onChange={(v) => update({ template: v })}
          options={(options?.templates ?? []).map((t) => ({ value: t, label: t }))} />
        <Input value={phoneInput} onChange={(e) => setPhoneInput(e.target.value)} placeholder="Number" className="w-36 font-mono" aria-label="Contact number" />
        <Input type="date" value={filters.from} onChange={(e) => update({ from: e.target.value })} className="w-40" aria-label="From date" />
        <Input type="date" value={filters.to} onChange={(e) => update({ to: e.target.value })} className="w-40" aria-label="To date" />
        <Button variant="outline" size="sm" onClick={reset} disabled={active === 0 && !qInput && !phoneInput}>
          Reset{active > 0 ? ` (${active})` : ''}
        </Button>
      </div>

      {error && <LoadError message={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Loading messages...</div>
      ) : items.length === 0 && !error ? (
        active > 0 ? (
          <p className="rounded-sm border border-line p-6 text-center text-xs text-steel">No messages match these filters.</p>
        ) : bridgeAvailable ? (
          <p className="rounded-sm border border-line p-6 text-center text-xs text-steel">No messages yet. Messages your agents send and receive appear here.</p>
        ) : (
          <BridgeUnavailable />
        )
      ) : (
        <div className="rounded-sm border border-line">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Direction</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Message</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Agent</TableHead>
                <TableHead>Gateway</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((m) => {
                const runPath = agentRunPath(m);
                const title = agentTitle(m.agent);
                return (
                  <TableRow key={m.name} className="cursor-pointer" onClick={() => setSelected(m)}>
                    <TableCell className="whitespace-nowrap font-mono text-xs text-steel">{m.creation}</TableCell>
                    <TableCell><Badge variant={m.direction === 'in' ? 'pill-neutral' : 'pill-success'}>{m.direction === 'in' ? 'In' : 'Out'}</Badge></TableCell>
                    <TableCell className="text-xs">
                      <div className="font-mono text-ink">{m.phone}</div>
                      {m.profile_name && <div className="text-steel">{m.profile_name}</div>}
                    </TableCell>
                    <TableCell className="max-w-md text-xs">
                      <div className="flex items-center gap-1.5">
                        {m.content_type && m.content_type !== 'text' && <Badge variant="chip" size="sm">{m.content_type}</Badge>}
                        {m.template && <Badge variant="pill-neutral">{m.template}</Badge>}
                        <span className="truncate text-ink">{messagePreview(m)}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusTicks status={m.status} />
                      {m.error && <div className="max-w-48 truncate text-[11px] text-destructive" title={m.error}>{m.error}</div>}
                    </TableCell>
                    <TableCell className="text-xs">
                      {runPath ? (
                        <Link to={runPath} onClick={(e) => e.stopPropagation()} className="text-signal-ink underline">{sentByLabel(m.sent_by, title ?? m.agent)}</Link>
                      ) : (
                        <span className="text-steel">{sentByLabel(m.sent_by, title ?? m.agent)}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-steel">{m.gateway}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {hasMore && (
            <div className="border-t border-line p-2 text-center">
              <Button variant="outline" size="sm" onClick={() => void loadMore()} disabled={loadingMore}>
                {loadingMore && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}Load more
              </Button>
            </div>
          )}
        </div>
      )}

      <MessageDetailSheet item={selected} agentTitle={agentTitle(selected?.agent ?? null)} gateway={gateway} onClose={() => setSelected(null)} />
    </div>
  );
}
