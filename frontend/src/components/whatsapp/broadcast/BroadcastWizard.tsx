import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Checkbox } from '@/components/ui/checkbox';
import { Field } from '@/components/ui/field';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { errorText, listTemplates, type WhatsAppTemplate } from '@/services/whatsappApi';
import { addBroadcastRecipients, attestBroadcastConsent, createBroadcast, deleteBroadcast, getBroadcastTemplateParams, previewBroadcast, startBroadcast, scheduleBroadcast, type AddRecipientsResult, type BroadcastPreview, type BroadcastRecipientInput, type BroadcastTemplateParams, type BroadcastTemplateVariable, toIssue, type BroadcastSendVia, adaptAddResult } from './broadcastApi';
import { toSiteDatetime } from './broadcastModel';
import type { AudienceSelectionItem, SelectionPreview } from '../audiences/audiencesApi';
import { RecipientsStep } from './recipients/RecipientsStep';
import { setBroadcastAudiences, type ConsentCover } from './recipients/audienceSelectionApi';
import { getBroadcastLimits, limitFlag, limitNumber, type BroadcastLimit } from './limitsApi';

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

export interface LocationValue { latitude: string; longitude: string; name: string; address: string }
const EMPTY_LOCATION: LocationValue = { latitude: '', longitude: '', name: '', address: '' };

const inRange = (v: string, max: number) => v.trim() !== '' && Number.isFinite(Number(v)) && Math.abs(Number(v)) <= max;
/** Latitude -90..90 and longitude -180..180 are both required for a location header. */
export const locationValid = (l: LocationValue) => inRange(l.latitude, 90) && inRange(l.longitude, 180);

/** Header / button parameters the operator filled in, in the shape `create_broadcast` takes (undefined when none). */
export function buildHeaderButtonParams(
  tpl: BroadcastTemplateParams | null, headerValue: string, buttonValues: Record<number, string>, location: LocationValue = EMPTY_LOCATION,
): { header_params?: unknown; button_params?: unknown } {
  const out: { header_params?: unknown; button_params?: unknown } = {};
  const h = headerValue.trim();
  if (tpl?.header && tpl.header.type === 'LOCATION') {
    if (locationValid(location)) {
      out.header_params = [{
        type: 'location', latitude: Number(location.latitude), longitude: Number(location.longitude),
        ...(location.name.trim() ? { name: location.name.trim() } : {}), ...(location.address.trim() ? { address: location.address.trim() } : {}),
      }];
    }
  } else if (tpl?.header && h) out.header_params = [h];
  const buttons = (tpl?.buttons ?? [])
    .filter((b) => b.sub_type !== 'quick_reply' && (buttonValues[b.index] ?? '').trim() !== '')
    .map((b) => (b.sub_type === 'copy_code'
      ? { index: b.index, sub_type: 'copy_code', code: buttonValues[b.index].trim() }
      : { index: b.index, sub_type: 'url', text: buttonValues[b.index].trim() }));
  if (buttons.length) out.button_params = buttons;
  return out;
}

/** A pasted list whose first line is a header (`phone,...`) is sent as CSV, so per-recipient header and button columns work. */
export const hasHeaderRow = (text: string) => /^(phone|recipient)\b/i.test(text.trim());

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
  const [selection, setSelection] = useState<AudienceSelectionItem[]>([]);
  const [audPreview, setAudPreview] = useState<SelectionPreview | null>(null);
  const [listsResult, setListsResult] = useState<AddRecipientsResult | null>(null);
  const [cover, setCover] = useState<ConsentCover | null>(null);
  const manualDone = useRef(false);
  const manualAdded = useRef(0);
  const [consent, setConsent] = useState(false);
  const [source, setSource] = useState('');
  const [preview, setPreview] = useState<BroadcastPreview | null>(null);
  const [typed, setTyped] = useState('');
  const [scheduleMode, setScheduleMode] = useState(false);
  const [scheduledAt, setScheduledAt] = useState('');
  const [broadcast, setBroadcast] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [tplParams, setTplParams] = useState<BroadcastTemplateParams | null>(null);
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [headerValue, setHeaderValue] = useState('');
  const [buttonValues, setButtonValues] = useState<Record<number, string>>({});
  const [location, setLocation] = useState<LocationValue>(EMPTY_LOCATION);
  const started = useRef(false);
  const [limits, setLimits] = useState<BroadcastLimit[] | null>(null);
  const [acked, setAcked] = useState<Record<string, boolean>>({});
  // Fallbacks equal the registry defaults, used only while the limits are unreadable.
  const locationMax = limitNumber(limits, 'location_text_max', 1000);
  const urlSuffixMax = limitNumber(limits, 'url_suffix_max', 200);
  const copyCodeMax = limitNumber(limits, 'copy_code_max', 15);
  const requireTyped = limitFlag(limits, 'require_typed_count', true);

  useEffect(() => {
    let live = true;
    void getBroadcastLimits().then((res) => { if (live && res.success) setLimits(res.limits); });
    return () => { live = false; };
  }, [gateway]);

  useEffect(() => {
    void listTemplates(gateway, 'APPROVED').then((res) => {
      if (res.success) setTemplates((res.templates ?? []).filter((t) => (t.status ?? 'APPROVED').toUpperCase() === 'APPROVED'));
      else { setTemplates([]); setErr(errorText(res)); }
    });
  }, [gateway]);

  useEffect(() => {
    setTplParams(null); setDefaults({}); setHeaderValue(''); setButtonValues({}); setLocation(EMPTY_LOCATION);
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
  const extraColumns = [
    ...(header ? (locationHeader ? ['header_lat', 'header_lng'] : ['header']) : []),
    ...urlButtons.map((b) => (b.sub_type === 'copy_code' ? `button_code_${b.index}` : `button_url_${b.index}`)),
  ];
  const paramsReady =
    (!header || !header.required || (locationHeader ? locationValid(location) : headerValue.trim() !== '')) &&
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
      const c = await createBroadcast({ gateway, template: tplName, title: title.trim() || `Broadcast ${tpl?.template_name ?? tplName}`, language_code: tpl?.language_code, send_via: isMarketing ? sendVia : 'messages', body_params: buildBodyParams(), ...buildHeaderButtonParams(tplParams, headerValue, buttonValues, location) });
      if (!c.success) return fail(c);
      id = c.broadcast;
      setBroadcast(id);
    }
    const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
    let added = 0;
    if ((csv !== null || lines.length) && !manualDone.current) {
      const res = await addBroadcastRecipients(id, csv !== null ? { csvText: csv } : hasHeaderRow(text) ? { csvText: text } : { recipients: parseRecipientLines(lines, named, vars) });
      if (!res.success) return fail(res);
      manualDone.current = true;
      manualAdded.current = res.added;
      setResult(res);
    }
    // Lists go in after the manual rows so the consent cover is computed over everything.
    if (selection.length) {
      const res = await setBroadcastAudiences(id, selection);
      if (!res.success) return fail(res);
      if (res.blocked.length) return fail({ success: false, error: 'audience_purpose_mismatch', message: res.blocked.map((b) => b.message).join(' ') });
      setListsResult(adaptAddResult(res));
      setCover(res.consent);
      added += res.added;
    }
    setBusy(false);
    setReviewing(added + manualAdded.current > 0);
    return true;
  };

  const submitConsent = async (): Promise<boolean> => {
    setBusy(true); setErr('');
    if (!covered) {
      const a = await attestBroadcastConsent(broadcast, source.trim());
      if (!a.success) return fail(a);
    }
    const p = await previewBroadcast(broadcast);
    if (!p.success) return fail(p);
    setPreview(p.preview);
    setAcked({});
    void getBroadcastLimits(broadcast).then((res) => { if (res.success) setLimits(res.limits); });
    setBusy(false);
    return true;
  };

  const start = async () => {
    setBusy(true); setErr('');
    const confirmCount = requireTyped ? typed.trim() : String(preview?.queued ?? '');
    const codes = (preview?.warnings ?? []).map((w) => toIssue(w).code);
    const res = scheduleMode ? await scheduleBroadcast(broadcast, toSiteDatetime(scheduledAt), confirmCount, codes) : await startBroadcast(broadcast, confirmCount, codes);
    if (!res.success && (res.error === 'warnings_changed' || res.error === 'recipients_changed')) {
      // The situation changed since the preview: show the new list and ask again.
      const p = await previewBroadcast(broadcast);
      if (p.success) { setPreview(p.preview); setAcked({}); setStep(3); }
      setBusy(false); setErr(res.error === 'recipients_changed' ? 'The recipient list changed since you reviewed this broadcast. Please review it again.' : 'Something changed since you reviewed this broadcast. Please review the warnings again.');
      return;
    }
    setBusy(false);
    if (!res.success) { setErr(errorText(res)); return; }
    started.current = true;
    toast.success(scheduleMode ? 'Broadcast scheduled' : 'Broadcast started');
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

  const covered = !!cover?.satisfied;
  const blocking = (preview?.blocking ?? []).map(toIssue);
  const warnings = (preview?.warnings ?? []).map(toIssue);
  const allAcked = warnings.every((w) => acked[w.code]);
  const applied = (preview?.limits_in_effect ?? []).map((k) => limits?.find((l) => l.key === k)).filter((l): l is BroadcastLimit => !!l);
  const expected = preview ? String(preview.queued) : '';
  const canNext = [
    !!tpl && paramsReady,
    (csv !== null || text.trim().length > 0 || selection.length > 0) && !(audPreview?.blocked.length) && !busy,
    (covered || (consent && source.trim().length > 0)) && !busy,
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
                    <Input id={`bc-var-${k}`} value={defaults[k] ?? ''} placeholder={v.sample ? `e.g. ${v.sample}` : ''} onChange={(e) => setDefaults((d) => ({ ...d, [k]: e.target.value }))} />
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
          {locationHeader ? (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Header location (the same place for every recipient unless a column says otherwise)</legend>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Latitude" id="bc-loc-lat" hint="-90 to 90" error={location.latitude && !inRange(location.latitude, 90) ? 'Enter a number between -90 and 90' : undefined}>
                  {(p) => <Input {...p} inputMode="decimal" value={location.latitude} onChange={(e) => setLocation((l) => ({ ...l, latitude: e.target.value }))} />}
                </Field>
                <Field label="Longitude" id="bc-loc-lng" hint="-180 to 180" error={location.longitude && !inRange(location.longitude, 180) ? 'Enter a number between -180 and 180' : undefined}>
                  {(p) => <Input {...p} inputMode="decimal" value={location.longitude} onChange={(e) => setLocation((l) => ({ ...l, longitude: e.target.value }))} />}
                </Field>
                <Field label="Place name (optional)" id="bc-loc-name">
                  {(p) => <Input {...p} maxLength={locationMax} value={location.name} onChange={(e) => setLocation((l) => ({ ...l, name: e.target.value }))} />}
                </Field>
                <Field label="Address (optional)" id="bc-loc-address">
                  {(p) => <Input {...p} maxLength={locationMax} value={location.address} onChange={(e) => setLocation((l) => ({ ...l, address: e.target.value }))} />}
                </Field>
              </div>
            </fieldset>
          ) : null}
          {urlButtons.map((b) => (
            <div key={b.index} className="space-y-1">
              <Label htmlFor={`bc-btn-${b.index}`}>{b.sub_type === 'copy_code' ? 'Coupon code' : 'Link suffix'} for button {b.label ? `"${b.label}"` : b.index + 1}{b.required ? '' : ' (optional)'}</Label>
              <Input id={`bc-btn-${b.index}`} value={buttonValues[b.index] ?? ''} maxLength={b.sub_type === 'copy_code' ? copyCodeMax : urlSuffixMax} onChange={(e) => setButtonValues((v) => ({ ...v, [b.index]: e.target.value }))} />
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

      {step === 1 && (
        <RecipientsStep
          gateway={gateway} templateCategory={tpl?.category} selection={selection} onSelection={setSelection}
          onAudiencePreview={setAudPreview} text={text} onText={setText} csv={csv} onFile={(f) => void onFile(f)}
          locked={reviewing} result={result} listsResult={listsResult}
          columnsHint={`${vars.length > 0
            ? `Columns: phone, ${vars.map((v, i) => varKey(v, i)).join(', ')} (comma or tab separated). Missing values use the defaults from step 1.`
            : 'Columns: phone.'}${extraColumns.length ? ` For per-recipient values, start with a header line such as phone,${extraColumns.join(',')}; an empty cell uses the default.` : ''}`}
        />
      )}

      {step === 2 && (
        covered ? (
          <p role="status" className="text-sm">Consent covered by: {cover?.audiences.map((a) => a.title ?? a.audience).join(', ')}. Each list was confirmed when it was created, so there is nothing more to confirm here.</p>
        ) : (
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
        )
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
          {applied.length ? (
            <div aria-label="Limits applied to this broadcast" role="group" className="rounded-md border p-3">
              <p className="font-medium">Limits applied to this broadcast</p>
              <ul className="list-disc pl-5 text-xs text-steel">
                {applied.map((l) => <li key={l.key}>{l.label}: {l.effective === null ? (l.kind === 'meta' ? 'not known yet' : 'no limit') : typeof l.effective === 'boolean' ? (l.effective ? 'on' : 'off') : `${l.effective}${l.unit ? ` ${l.unit}` : ''}`}</li>)}
              </ul>
            </div>
          ) : null}
          {warnings.length ? (
            <Alert variant="warning" className="space-y-2">
              <p className="font-medium">Warnings</p>
              {warnings.map((w) => (
                <div key={w.code} className="flex items-start gap-2">
                  <Checkbox id={`bc-ack-${w.code}`} checked={!!acked[w.code]} onCheckedChange={(v) => setAcked((a) => ({ ...a, [w.code]: v === true }))} />
                  <Label htmlFor={`bc-ack-${w.code}`}><span>{w.message}</span> <span className="block text-xs">I understand, continue anyway.</span></Label>
                </div>
              ))}
            </Alert>
          ) : null}
          {blocking.length ? (
            <div role="alert" className="text-destructive">
              <p className="font-medium">Cannot start</p>
              <ul className="list-disc pl-5">{blocking.map((w) => <li key={w.code}>{w.message}</li>)}</ul>
              <p className="mt-1 text-xs text-steel">The template values are fixed once recipients are added. Discard this draft and start again with the missing values.</p>
            </div>
          ) : null}
        </div>
      )}

      {step === 4 && preview && (
        <div className="space-y-2">
          {requireTyped ? (
            <>
              <Label htmlFor="bc-confirm">Type {expected} to confirm sending to {expected} recipients</Label>
              <Input id="bc-confirm" inputMode="numeric" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
            </>
          ) : <p className="text-sm">Ready to send to <strong>{expected}</strong> recipients.</p>}
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">When to send</legend>
            <RadioGroup
              aria-label="When to send"
              value={scheduleMode ? 'later' : 'now'}
              onValueChange={(v) => setScheduleMode(v === 'later')}
              className="flex items-center gap-2"
            >
              <RadioGroupItem value="now" id="bc-send-now" />
              <Label htmlFor="bc-send-now">Send now</Label>
              <RadioGroupItem value="later" id="bc-send-later" />
              <Label htmlFor="bc-send-later">Schedule for</Label>
            </RadioGroup>
            {scheduleMode ? (
              <div className="space-y-1">
                <Input id="bc-schedule-at" type="datetime-local" aria-label="Schedule date and time" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} />
                <p className="text-xs text-steel">Time is in the site timezone. The broadcast starts within 5 minutes of this time.</p>
              </div>
            ) : null}
          </fieldset>
        </div>
      )}

      <div className="flex justify-between">
        <Button variant="outline" disabled={busy || step === 0 || (!!broadcast && step <= 2)} onClick={() => setStep((s) => s - 1)}>Back</Button>
        {step < 4 ? (
          <Button disabled={busy || (step === 1 && reviewing ? false : step === 3 ? blocking.length > 0 || !allAcked : !canNext)} onClick={() => (step === 1 && reviewing) ? setStep(2) : step === 3 ? setStep(4) : void next()}>
            {busy ? 'Working...' : step === 1 && reviewing ? 'Continue' : step === 1 ? 'Add recipients' : 'Next'}
          </Button>
        ) : (
          <Button variant="destructive" disabled={busy || blocking.length > 0 || (requireTyped && typed.trim() !== expected) || !expected || (scheduleMode && !scheduledAt)} onClick={() => void start()}>{scheduleMode ? 'Schedule broadcast' : 'Start broadcast'}</Button>
        )}
      </div>
    </section>
  );
}
