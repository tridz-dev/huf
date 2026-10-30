import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { errorText } from '@/services/whatsappApi';
import { getAudience, listMembers, removeMembers, type AudienceMember } from './audiencesApi';

const ALL = '__all__';
const PAGE_SIZE = 50;
const SUPPRESSED_LABEL: Record<string, string> = { opted_out: 'Opted out', marketing_opted_out: 'Opted out of marketing' };

export function MemberTable({ audience, refreshKey = 0, onChanged }: { audience: string; refreshKey?: number; onChanged?: () => void }) {
  const [q, setQ] = useState('');
  const [tag, setTag] = useState('');
  const [suppressedOnly, setSuppressedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [members, setMembers] = useState<AudienceMember[] | null>(null);
  const [total, setTotal] = useState(0);
  const [tagOptions, setTagOptions] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [masked, setMasked] = useState(true);

  const load = useCallback(async () => {
    const res = await listMembers(audience, { search: q.trim() || undefined, tags: tag ? [tag] : undefined, suppressed: suppressedOnly || undefined }, page, PAGE_SIZE);
    if (!res.success) { setError(errorText(res)); setMembers([]); return; }
    setError('');
    setMembers(res.members);
    setTotal(res.total);
    setMasked(res.masked);
  }, [audience, q, tag, suppressedOnly, page]);

  useEffect(() => {
    void getAudience(audience).then((r) => { if (r.success) setTagOptions(r.audience.tags.map((t) => t.tag)); });
  }, [audience, refreshKey]);

  useEffect(() => {
    const t = setTimeout(() => void load(), q ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, refreshKey, q]);

  const remove = async (m: AudienceMember) => {
    const res = await removeMembers(audience, [m.recipient]);
    if (!res.success) { toast.error(errorText(res)); return; }
    toast.success('Contact removed');
    void load();
    onChanged?.();
  };

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end">
        <Field label="Search" id="mem-q">
          <Input id="mem-q" placeholder="Number" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </Field>
        <Field label="Tag" id="mem-tag">
          {(p) => (
            <Select value={tag || ALL} onValueChange={(v) => { setTag(v === ALL ? '' : v); setPage(1); }}>
              <SelectTrigger {...p} className="w-full" aria-label="Tag"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All tags</SelectItem>
                {tagOptions.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
        </Field>
        <div className="flex items-center gap-2 pb-2 text-sm">
          <Checkbox aria-label="Only opted-out" checked={suppressedOnly} onCheckedChange={(c) => { setSuppressedOnly(c === true); setPage(1); }} />
          Only opted-out
        </div>
      </div>
      {masked && <p className="text-xs text-steel">Numbers are hidden. Only people who manage this WhatsApp gateway can see them.</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {members && members.length === 0 && !error ? (
        <p className="text-sm text-steel">No contacts match.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Number</TableHead><TableHead>Name</TableHead><TableHead>Tags</TableHead><TableHead>Status</TableHead><TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(members ?? []).map((m, i) => (
              <TableRow key={`${m.recipient}-${i}`}>
                <TableCell>{m.recipient}</TableCell>
                <TableCell>{m.display_name || '-'}</TableCell>
                <TableCell className="space-x-1">{m.tags.map((t) => <Badge key={t} variant="secondary">{t}</Badge>)}</TableCell>
                <TableCell>
                  {m.suppressed ? <Badge variant="destructive">{SUPPRESSED_LABEL[m.suppressed] ?? 'Opted out'}</Badge> : 'Active'}
                </TableCell>
                <TableCell className="text-right">
                  {!masked && (
                    <Button variant="ghost" size="sm" aria-label={`Remove ${m.recipient}`} onClick={() => void remove(m)}>Remove</Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <div className="flex items-center justify-between text-xs text-steel">
        <span>{total} contacts</span>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>Previous</Button>
          <span>Page {page} of {pages}</span>
          <Button variant="ghost" size="sm" disabled={page >= pages} onClick={() => setPage((n) => n + 1)}>Next</Button>
        </div>
      </div>
    </div>
  );
}
