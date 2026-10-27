import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Field } from '@/components/ui/field';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { errorText, listTemplates, type WhatsAppTemplate } from '@/services/whatsappApi';
import { addBroadcastRecipients, attestBroadcastConsent, createBroadcast, deleteBroadcast, getBroadcastTemplateParams, previewBroadcast, startBroadcast, type AddRecipientsResult, type BroadcastPreview, type BroadcastRecipientInput, type BroadcastTemplateParams, type BroadcastTemplateVariable, type BroadcastSendVia } from './broadcastApi';

const varKey = (v: BroadcastTemplateVariable, i: number) => (v.name ?? String(v.index ?? i + 1));

/** Lines are `phone` or `phone,v1,v2` (comma or tab). Values map to template variables in order. */
export function parseRecipientLines(lines: string[], named: boolean, vars: BroadcastTemplateVariable[]): BroadcastRecipientInput[] {
  return lines.map((line) => {
    const [recipient, ...cells] = line.split(/[,\t]/).map((c) => c.trim());
    const vals = cells.slice(0, vars.length);
    if (!vals.some((c) => c !== '')) return { recipient };
    if (named) {
      const body: Record<string, string> = {};
      vals.forEach((v, i) => { if (v !== '') body[vars[i].name ?? String(i + 1)] = v; });
      return { recipient, params: { body } };
    }
    return { recipient, params: { body: vals } };
  });
}

/** Header / button parameters the operator filled in, in the shape `create_broadcast` takes (undefined when none). */
export function buildHeaderButtonParams(
  tpl: BroadcastTemplateParams | null, headerValue: string, buttonValues: Record<number, string>,
): { header_params?: unknown; button_params?: unknown } {
  const out: { header_params?: unknown; button_params?: unknown } = {};
  const h = headerValue.trim();
  if (tpl?.header && h && tpl.header.type !== 'LOCATION') out.header_params = [h];
  const buttons = (tpl?.buttons ?? [])
    .filter((b) => b.sub_type !== 'quick_reply' && (buttonValues[b.index] ?? '').trim() !== '')
    .map((b) => (b.sub_type === 'copy_code'
      ? { index: b.index, sub_type: 'copy_code', code: buttonValues[b.index].trim() }
      : { index: b.index, sub_type: 'url', text: buttonValues[b.index].trim() }));
  if (buttons.length) out.button_params = buttons;
  return out;
}

const STEPS = ['Template', 'Recipients', 'Consent', 'Preview', 'Confirm'] as const;

export function BroadcastWizard({ gateway, onClose, onStarted }: { gateway: string; onClose: () => void; onStarted: (name: string) => void }) {
  const [step, setStep] = useState(0);
  const [templates, setTemplates] = useState<WhatsAppTemplate[] | null>(null);
  const [tplName, setTplName] = useState('');
  const [title, setTitle] = useState('');
  const [sendVia, setSendVia] = useState<BroadcastSendVia>('messages');
  const [text, setText] = useState('');
  const [csv, setCsv] = useState<string | null>(null);
  const [result, setResult] = useState<AddRecipientsResult | null>(null);
  const [consent, setConsent] = useState(false);
  const [source, setSource] = useState('');
  const [preview, setPreview] = useState<BroadcastPreview | null>(null);
  const [typed, setTyped] = useState('');
  const [broadcast, setBroadcast] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [tplParams, setTplParams] = useState<BroadcastTemplateParams | null>(null);
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [headerValue, setHeaderValue] = useState('');
  const [buttonValues, setButtonValues] = useState<Record<number, string>>({});
  const started = useRef(false);

  useEffect(() => {
    void listTemplates(gateway, 'APPROVED').then((res) => {
      if (res.success) setTemplates((res.templates ?? []).filter((t) => (t.status ?? 'APPROVED').toUpperCase() === 'APPROVED'));
      else { setTemplates([]); setErr(errorText(res)); }
    });
  }, [gateway]);

  useEffect(() => {
    setTplParams(null); setDefaults({}); setHeaderValue(''); setButtonValues({});
    if (!tplName) return;
    let live = true;
    void getBroadcastTemplateParams(gateway, tplName).then((res) => {
      if (!live) return;
      if (res.success) setTplParams(res); else setErr(errorText(res));
    });
    return () => { live = false; };
  }, [gateway, tplName]);

  const vars = tplParams?.body ?? [];
  const named = tplParams?.parameter_format === 'NAMED';
  const header = tplParams?.header ?? null;
  const urlButtons = (tplParams?.buttons ?? []).filter((b) => b.sub_type !== 'quick_reply');
  const headerType = (header?.type ?? '').toUpperCase();
  const locationHeader = headerType === 'LOCATION';
  const headerIsMedia = !!header && headerType !== 'TEXT';
  const paramsReady =
    (!header || !header.required || locationHeader || headerValue.trim() !== '') &&
    urlButtons.every((b) => !b.required || (buttonValues[b.index] ?? '').trim() !== '');

  const buildBodyParams = (): Record<string, string> | string[] | undefined => {
    if (!vars.some((v, i) => (defaults[varKey(v, i)] ?? '').trim() !== '')) return undefined;
    if (named) {
      const o: Record<string, string> = {};
      vars.forEach((v, i) => { const x = (defaults[varKey(v, i)] ?? '').trim(); if (x) o[v.name ?? String(i + 1)] = x; });
      return o;
    }
    return vars.map((v, i) => (defaults[varKey(v, i)] ?? '').trim());
  };

  const tpl = templates?.find((t) => t.name === tplName);
  const isMarketing = (tpl?.category ?? '').toUpperCase() === 'MARKETING';
  const fail = (res: Parameters<typeof errorText>[0]) => { setErr(errorText(res)); setBusy(false); return false; };

  const submitRecipients = async (): Promise<boolean> => {
    setBusy(true); setErr('');
    let id = broadcast;
    if (!id) {
      const c = await createBroadcast({ gateway, template: tplName, title: title.trim() || `Broadcast ${tpl?.template_name ?? tplName}`, language_code: tpl?.language_code, send_via: isMarketing ? sendVia : 'messages', body_params: buildBodyParams(), ...buildHeaderButtonParams(tplParams, headerValue, buttonValues) });
      if (!c.success) return fail(c);
      id = c.broadcast;
      setBroadcast(id);
    }
    const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
    const res = await addBroadcastRecipients(id, csv !== null ? { csvText: csv } : { recipients: parseRecipientLines(lines, named, vars) });
    if (!res.success) return fail(res);
    setResult(res);
    setBusy(false);
    setReviewing(res.added > 0);
    return true;
  };

  const submitConsent = async (): Promise<boolean> => {
    setBusy(true); setErr('');
    const a = await attestBroadcastConsent(broadcast, source.trim());
    if (!a.success) return fail(a);
    const p = await previewBroadcast(broadcast);
    if (!p.success) return fail(p);
    setPreview(p.preview);
    setBusy(false);
    return true;
  };

  const start = async () => {
    setBusy(true); setErr('');
    const res = await startBroadcast(broadcast, typed.trim());
    setBusy(false);
    if (!res.success) { setErr(errorText(res)); return; }
    started.current = true;
    toast.success('Broadcast started');
    onStarted(broadcast);
  };

  /** Closing before the start must not leave an orphan Draft behind. */
  const close = async () => {
    if (broadcast && !started.current) {
      setBusy(true);
      const res = await deleteBroadcast(broadcast);
      setBusy(false);
      if (!res.success) { toast.error(errorText(res)); return; }
    }
    onClose();
  };

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    setCsv(await f.text());
    setText('');
  };

  const blocking = preview?.blocking ?? [];
  const expected = preview ? String(preview.queued) : '';
  const canNext = [
    !!tpl && paramsReady && !locationHeader,
    (csv !== null || text.trim().length > 0) && !busy,
    consent && source.trim().length > 0 && !busy,
  ][step];

  const next = async () => {
    if (step === 1) { await submitRecipients(); return; }
    if (step === 2 && !(await submitConsent())) return;
    setStep((s) => s + 1);
  };

  return (
    <section aria-label="New broadcast" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-ink">New broadcast</h2>
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => void close()}>{broadcast ? 'Discard draft' : 'Close'}</Button>
      </div>
      <ol className="flex flex-wrap gap-2 text-xs text-steel" aria-label="Steps">
        {STEPS.map((s, i) => <li key={s} aria-current={step === i ? 'step' : undefined} className={step === i ? 'font-semibold text-ink' : ''}>{i + 1}. {s}</li>)}
      </ol>
      {err ? <p role="alert" className="text-sm text-destructive">{err}</p> : null}

      {step === 0 && (
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="bc-title">Title</Label>
            <Input id="bc-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <Field label="Approved template" id="bc-template">
            {(p) => (
              <Select value={tplName || undefined} onValueChange={(v) => { setTplName(v); setSendVia('messages'); }}>
                <SelectTrigger {...p} className="w-full" aria-label="Approved template">
                  <SelectValue placeholder={templates ? 'Choose a template' : 'Loading...'} />
                </SelectTrigger>
                <SelectContent>
                  {(templates ?? []).map((t) => <SelectItem key={t.name} value={t.name}>{t.template_name} ({t.language_code})</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </Field>
          {tpl ? (
            <p className="text-sm text-steel">
              Category: <strong>{tpl.category ?? 'unknown'}</strong>.
              {(tpl.category ?? '').toUpperCase() === 'MARKETING'
                ? ' Marketing messages are billed per delivered message and are limited to contacts who opted in to marketing.'
                : ''}
            </p>
          ) : null}
          {vars.length > 0 ? (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Template variables (defaults for every recipient)</legend>
              {vars.map((v, i) => {
                const k = varKey(v, i);
                return (
                  <div key={k} className="space-y-1">
                    <Label htmlFor={`bc-var-${k}`}>Default value for {`{{${k}}}`}</Label>
                    <Input id={`bc-var-${k}`} value={defaults[k] ?? ''} placeholder={v.sample ?? ''} onChange={(e) => setDefaults((d) => ({ ...d, [k]: e.target.value }))} />
                  </div>
                );
              })}
            </fieldset>
          ) : null}
          {header && !locationHeader ? (
            <div className="space-y-1">
              <Label htmlFor="bc-header">{headerIsMedia ? `Header ${headerType.toLowerCase()} link (https)` : 'Header text value'}{header.required ? '' : ' (optional)'}</Label>
              <Input id="bc-header" value={headerValue} placeholder={headerIsMedia ? 'https://example.com/file' : (header.sample ?? '')} onChange={(e) => setHeaderValue(e.target.value)} />
            </div>
          ) : null}
          {locationHeader ? <p role="note" className="text-xs text-steel">Templates with a location header cannot be broadcast from here yet.</p> : null}
          {urlButtons.map((b) => (
            <div key={b.index} className="space-y-1">
              <Label htmlFor={`bc-btn-${b.index}`}>{b.sub_type === 'copy_code' ? 'Coupon code' : 'Link suffix'} for button {b.label ? `"${b.label}"` : b.index + 1}{b.required ? '' : ' (optional)'}</Label>
              <Input id={`bc-btn-${b.index}`} value={buttonValues[b.index] ?? ''} maxLength={b.sub_type === 'copy_code' ? 15 : 200} onChange={(e) => setButtonValues((v) => ({ ...v, [b.index]: e.target.value }))} />
            </div>
          ))}
          {isMarketing ? (
            <Field
              label="Send via"
              id="bc-send-via"
              hint="The Marketing Messages API uses a separate endpoint and falls back to the Cloud API if the account is not onboarded. Cloud API marketing sends are sunset in 2027."
            >
              {(p) => (
                <Select value={sendVia} onValueChange={(v) => setSendVia(v as BroadcastSendVia)}>
                  <SelectTrigger {...p} className="w-full" aria-label="Send via"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="messages">Cloud API (messages)</SelectItem>
                    <SelectItem value="marketing_messages">Marketing Messages API (marketing_messages)</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </Field>
          ) : null}
        </div>
      )}

      {(step === 1) && (
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="bc-recipients">Recipients (one phone number per line)</Label>
            <Textarea id="bc-recipients" rows={8} value={text} disabled={reviewing || csv !== null} onChange={(e) => setText(e.target.value)} placeholder="+14155550101" />
            <p className="text-xs text-steel">
              {vars.length > 0
                ? `Columns: phone, ${vars.map((v, i) => varKey(v, i)).join(', ')} (comma or tab separated). Missing values use the defaults from step 1.`
                : 'Columns: phone.'}
            </p>
          </div>
          <div className="space-y-1">
            <Label htmlFor="bc-csv">Or upload a CSV (header: phone)</Label>
            <Input id="bc-csv" type="file" accept=".csv,text/csv" disabled={reviewing} onChange={(e) => void onFile(e.target.files?.[0])} />
            {csv !== null ? <p className="text-xs text-steel">CSV loaded ({csv.split('\n').length - 1} rows)</p> : null}
          </div>
          {result ? (
            <div role="status" className="rounded-md border p-3 text-sm">
              <p><strong>{result.added}</strong> recipients added.</p>
              {result.invalidTotal ? (
                <div><p>{result.invalidTotal} invalid{result.invalidTotal > result.invalid.length ? ` (showing ${result.invalid.length})` : ''}:</p>
                  <ul className="list-disc pl-5">{result.invalid.map((x, i) => <li key={i}>{x.recipient ?? ''}{x.reason ? `: ${x.reason}` : ''}</li>)}</ul></div>
              ) : null}
              {result.skippedTotal ? (
                <div><p>{result.skippedTotal} skipped{result.skippedTotal > result.skipped.length ? ` (showing ${result.skipped.length})` : ''}:</p>
                  <ul className="list-disc pl-5">{result.skipped.map((x, i) => <li key={i}>{x.recipient}: {x.reason}</li>)}</ul></div>
              ) : null}
              {result.added === 0 ? <p className="text-destructive">No valid recipients. Fix the list and try again.</p> : null}
            </div>
          ) : null}
        </div>
      )}

      {step === 2 && (
        <div className="space-y-3">
          <div className="flex items-start gap-2">
            <Checkbox id="bc-consent" checked={consent} onCheckedChange={(v) => setConsent(v === true)} />
            <Label htmlFor="bc-consent">I confirm every recipient gave opt-in consent to receive these WhatsApp messages from this business.</Label>
          </div>
          <div className="space-y-1">
            <Label htmlFor="bc-source">Consent source (where and how consent was collected)</Label>
            <Input id="bc-source" value={source} onChange={(e) => setSource(e.target.value)} />
          </div>
        </div>
      )}

      {step === 3 && preview && (
        <div className="space-y-2 text-sm">
          <p>Recipients: <strong>{preview.recipients}</strong> ({preview.queued} will send, {preview.skipped} skipped). Category: {preview.category ?? 'unknown'}.{isMarketing ? ` Sending via ${sendVia === 'marketing_messages' ? 'Marketing Messages API' : 'Cloud API'}.` : ''}</p>
          <p>
            Messaging limit: {preview.within_limit === null ? 'unknown' : preview.within_limit ? 'within limit' : 'over limit'}
            {preview.remaining_24h !== null ? ` (${preview.remaining_24h} remaining in 24h)` : ''}.
          </p>
          <p>
            Estimated cost: {preview.cost?.total != null ? `${preview.cost.currency} ${preview.cost.total.toFixed(2)}` : 'unavailable (no verified rate for some recipients)'}.
            {preview.cost?.disclaimer ? <span className="text-xs text-steel"> {preview.cost.disclaimer}</span> : null}
          </p>
          {preview.cost?.warnings?.length ? (
            <ul className="list-disc pl-5 text-xs text-steel">{preview.cost.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          ) : null}
          {preview.warnings.length ? (
            <div role="alert" className="rounded-md border border-amber-500 bg-amber-50 p-3 text-amber-900 dark:bg-amber-950 dark:text-amber-100"><p className="font-medium">Warnings</p><ul className="list-disc pl-5">{preview.warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>
          ) : null}
          {blocking.length ? (
            <div role="alert" className="text-destructive"><p className="font-medium">Cannot start</p><ul className="list-disc pl-5">{blocking.map((w) => <li key={w}>{w}</li>)}</ul></div>
          ) : null}
        </div>
      )}

      {step === 4 && preview && (
        <div className="space-y-2">
          <Label htmlFor="bc-confirm">Type {expected} to confirm sending to {expected} recipients</Label>
          <Input id="bc-confirm" inputMode="numeric" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        </div>
      )}

      <div className="flex justify-between">
        <Button variant="outline" disabled={busy || step === 0 || (step === 1 && reviewing)} onClick={() => setStep((s) => s - 1)}>Back</Button>
        {step < 4 ? (
          <Button disabled={busy || (step === 1 && reviewing ? false : step === 3 ? blocking.length > 0 : !canNext)} onClick={() => (step === 1 && reviewing) ? setStep(2) : step === 3 ? setStep(4) : void next()}>
            {busy ? 'Working...' : step === 1 && reviewing ? 'Continue' : step === 1 ? 'Add recipients' : 'Next'}
          </Button>
        ) : (
          <Button variant="destructive" disabled={busy || blocking.length > 0 || typed.trim() !== expected || !expected} onClick={() => void start()}>Start broadcast</Button>
        )}
      </div>
    </section>
  );
}
