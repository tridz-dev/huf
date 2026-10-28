import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { errorText } from '@/services/whatsappApi';
import { getImportStatus, importMembers, type ImportStatus, type ImportTotals, type OnConflict } from './audiencesApi';
import { csvToObjects, guessPhoneColumn } from './csv';

const NONE = '__none__';
const CONFLICTS: { value: OnConflict; label: string }[] = [
  { value: 'skip', label: 'Keep the existing contact' },
  { value: 'update', label: 'Update name and values (tags are merged)' },
  { value: 'fail', label: 'Stop if any contact already exists' },
];
const POLL_MS = 1500;

interface Props { audience: string; title: string; onClose: () => void; onDone: () => void }

function ColumnSelect({ label, id, headers, value, onChange, optional }: {
  label: string; id: string; headers: string[]; value: string; onChange: (v: string) => void; optional?: boolean;
}) {
  return (
    <Field label={label} id={id}>
      {(p) => (
        <Select value={value || (optional ? NONE : undefined)} onValueChange={(v) => onChange(v === NONE ? '' : v)}>
          <SelectTrigger {...p} className="w-full" aria-label={label}><SelectValue placeholder="Choose a column" /></SelectTrigger>
          <SelectContent>
            {optional && <SelectItem value={NONE}>Not in file</SelectItem>}
            {headers.map((h) => <SelectItem key={h} value={h}>{h}</SelectItem>)}
          </SelectContent>
        </Select>
      )}
    </Field>
  );
}

export function ImportMembersDialog({ audience, title, onClose, onDone }: Props) {
  const [text, setText] = useState('');
  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [tags, setTags] = useState('');
  const [paramCols, setParamCols] = useState<string[]>([]);
  const [conflict, setConflict] = useState<OnConflict>('skip');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [result, setResult] = useState<ImportTotals | null>(null);
  const [job, setJob] = useState<string | null>(null);
  const [progress, setProgress] = useState<ImportStatus | null>(null);

  const parsed = useMemo(() => csvToObjects(text), [text]);
  const setCsv = (t: string) => {
    setText(t);
    const h = csvToObjects(t).headers;
    setPhone(guessPhoneColumn(h));
    setName(h.find((x) => /name/i.test(x)) ?? '');
    setTags(h.find((x) => /tag|label|group/i.test(x)) ?? '');
    setParamCols([]);
  };
  const onFile = async (f: File | undefined) => { if (f) setCsv(await f.text()); };
  const extra = parsed.headers.filter((h) => h !== phone && h !== name && h !== tags);

  useEffect(() => {
    if (!job) return undefined;
    let stop = false;
    const tick = async () => {
      const res = await getImportStatus(audience, job);
      if (stop) return;
      if (!res.success) { setErr(errorText(res)); setJob(null); return; }
      setProgress(res);
      if (res.status === 'done' && res.result) { setJob(null); setResult(res.result); toast.success('Import finished'); onDone(); }
      else if (res.status === 'failed') { setJob(null); setErr(res.error || 'The import failed.'); }
    };
    const id = setInterval(() => void tick(), POLL_MS);
    return () => { stop = true; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job, audience]);

  const run = async () => {
    if (!parsed.rows.length) { setErr('Paste or upload a CSV with a header row and at least one contact.'); return; }
    if (!phone) { setErr('Choose which column has the phone number.'); return; }
    setBusy(true); setErr('');
    const res = await importMembers({
      audience, csv_text: text, on_conflict: conflict,
      mapping: { phone, name: name || undefined, tags: tags || undefined, params: paramCols.length ? paramCols : undefined },
    });
    setBusy(false);
    if (!res.success) { setErr(errorText(res)); return; }
    if (res.queued) { setJob(res.job_id); setProgress(null); return; }
    setResult(res);
    toast.success('Import finished');
    onDone();
  };

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import contacts into {title}</DialogTitle>
          <DialogDescription>Upload a CSV file or paste it below. The first row must be the column names.</DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="space-y-2" role="status">
            <p className="text-sm">
              {result.added} added, {result.updated} updated, {result.skipped_total} skipped, {result.invalid_total} not valid.
            </p>
          </div>
        ) : job ? (
          <p role="status" className="text-sm">
            Importing in the background{progress ? `: ${progress.processed} of ${progress.total} contacts` : '...'}. You can close this window.
          </p>
        ) : (
          <div className="space-y-3">
            <Field label="CSV file" id="imp-file">
              <Input id="imp-file" type="file" accept=".csv,text/csv" onChange={(e) => void onFile(e.target.files?.[0])} />
            </Field>
            <Field label="Or paste CSV" id="imp-text" hint={parsed.rows.length ? `${parsed.rows.length} contacts found` : undefined}>
              <Textarea id="imp-text" rows={5} value={text} onChange={(e) => setCsv(e.target.value)} />
            </Field>
            {parsed.headers.length > 0 && (
              <>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <ColumnSelect label="Phone column" id="imp-phone" headers={parsed.headers} value={phone} onChange={setPhone} />
                  <ColumnSelect label="Name column" id="imp-name" headers={parsed.headers} value={name} onChange={setName} optional />
                  <ColumnSelect label="Tags column" id="imp-tags" headers={parsed.headers} value={tags} onChange={setTags} optional />
                </div>
                {extra.length > 0 && (
                  <fieldset className="space-y-2">
                    <legend className="text-sm font-medium">Template values (optional)</legend>
                    <p className="text-xs text-steel">Ticked columns fill the template's variables, in the order they appear in the file.</p>
                    {extra.map((h) => (
                      <div key={h} className="flex items-center gap-2 text-sm">
                        <Checkbox
                          aria-label={`Use ${h} as a template value`}
                          checked={paramCols.includes(h)}
                          onCheckedChange={(c) => setParamCols(extra.filter((x) => (x === h ? c === true : paramCols.includes(x))))}
                        />
                        {h}
                      </div>
                    ))}
                  </fieldset>
                )}
              </>
            )}
            <Field label="If a contact is already in this audience" id="imp-conflict">
              {(p) => (
                <Select value={conflict} onValueChange={(v) => setConflict(v as OnConflict)}>
                  <SelectTrigger {...p} className="w-full" aria-label="If a contact is already in this audience"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CONFLICTS.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            </Field>
            {busy && <p role="status" className="text-sm text-steel">Importing contacts...</p>}
            {err && <p role="alert" className="text-sm text-destructive">{err}</p>}
          </div>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>{result || job ? 'Close' : 'Cancel'}</Button>
          {!result && !job && <Button disabled={busy} onClick={() => void run()}>Import contacts</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
