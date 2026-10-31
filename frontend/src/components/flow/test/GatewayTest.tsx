import { useEffect, useMemo, useState } from 'react';
import { History, Loader2, MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useGatewayRegistry } from '@/hooks/flow/useGatewayRegistry';
import { GATEWAY_TRIGGER_KINDS } from '@/lib/flow-gateway/triggerKinds';
import { triggerResult } from '@/lib/flow-test/triggerResult';
import { ageText } from '@/lib/flow-test/testModel';
import { parseServerDate } from '@/lib/serverTime';
import { getGatewaySample, getLastGatewayMessage } from '@/services/flow/gateway/samplesApi';
import type { StepTestResult } from '@/services/flow/stepTestApi';
import type { GatewayPayloadField } from '@/lib/flow-gateway/gatewayTrigger.types';

interface Props {
  flowId: string;
  nodeId: string;
  kind: 'gateway' | 'whatsapp' | 'telegram';
  onResult: (result: StepTestResult) => void;
}

const messageOf = (error: unknown, fallback: string) => (error instanceof Error && error.message ? error.message : fallback);
const fieldKey = (f: GatewayPayloadField) => f.path.replace(/^input\./, '');
/** Only plain, short, non-secret things a person would type in a pretend message. */
const editable = (f: GatewayPayloadField) => !f.advanced && !f.sensitive && (f.type === 'text' || f.type === 'number');
const ALWAYS = new Set(['text', 'display_name']);
/** The pretend message lists what a sample really has (plus the message and the sender), not every field a channel could ever send. */
const hasValue = (v: unknown) => v !== '' && v !== null && v !== undefined;

/**
 * Test tab of a chat trigger (WhatsApp, Telegram, any channel). It never sends and never records a message: it fills
 * the data the flow starts with from a sample (editable) or from the last real message (numbers masked).
 */
export function GatewayTest({ flowId, nodeId, kind, onResult }: Props) {
  const { registry } = useGatewayRegistry();
  const spec = registry?.specs[GATEWAY_TRIGGER_KINDS.find((k) => k.id === kind)?.nodeType ?? 'trigger.gateway'];
  const [base, setBase] = useState<Record<string, unknown> | null>(null);
  const fields = useMemo(
    () => (spec?.payload_fields ?? []).filter((f) => editable(f) && (ALWAYS.has(fieldKey(f)) || hasValue((base ?? {})[fieldKey(f)] ?? f.sample))),
    [spec, base],
  );
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<'sample' | 'last' | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = (sample: Record<string, unknown>) => {
    setBase(sample);
    setValues(Object.fromEntries((spec?.payload_fields ?? []).filter(editable).map((f) => [fieldKey(f), String(sample[fieldKey(f)] ?? '')])));
  };
  useEffect(() => {
    if (!base && spec) load(Object.fromEntries(spec.payload_fields.map((f) => [fieldKey(f), f.sample])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec]);

  const useSample = async () => {
    setBusy('sample');
    setNote(null);
    try {
      const out = await getGatewaySample(flowId, nodeId);
      if (out.sample) load(out.sample);
      setNote('A sample message is filled in below. Change anything you like, then use it.');
    } catch (error) {
      setNote(messageOf(error, 'Could not load a sample message.'));
    } finally {
      setBusy(null);
    }
  };

  const useLast = async () => {
    setBusy('last');
    setNote(null);
    try {
      const out = await getLastGatewayMessage(flowId, nodeId);
      if (out.found && out.sample) {
        onResult(triggerResult(out.sample, `The last message this flow received${out.received_at ? `, ${ageText(parseServerDate(out.received_at))}` : ''}. Phone numbers are hidden.`));
      } else setNote('No message has started this flow yet. Use a sample message instead.');
    } catch (error) {
      setNote(messageOf(error, 'Could not load the last message.'));
    } finally {
      setBusy(null);
    }
  };

  const useEdited = () => {
    const sample: Record<string, unknown> = { ...(base ?? {}) };
    for (const f of fields) {
      const raw = values[fieldKey(f)] ?? '';
      sample[fieldKey(f)] = f.type === 'number' && raw.trim() !== '' && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
    }
    if (sample.text !== undefined) sample.message = sample.text;
    onResult(triggerResult(sample, 'A sample message. Nothing is sent.'));
  };

  return (
    <div className="space-y-3" data-testid="flow-step-test-gateway">
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={useLast} disabled={busy !== null} data-testid="flow-step-test-gateway-last">
          {busy === 'last' ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <History className="mr-1.5 h-4 w-4" aria-hidden />}
          Use last real message
        </Button>
        <Button type="button" variant="outline" onClick={useSample} disabled={busy !== null} data-testid="flow-step-test-gateway-sample">
          {busy === 'sample' ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <MessageSquare className="mr-1.5 h-4 w-4" aria-hidden />}
          Use a sample message
        </Button>
      </div>
      <p className="text-xs text-muted-foreground" data-testid="flow-step-test-gateway-note">Nothing is sent. This only shows the data the steps after it would get.</p>
      {fields.length > 0 && (
        <div className="space-y-2 rounded-md border border-border p-3" data-testid="flow-step-test-gateway-form">
          {fields.map((f) => (
            <div key={f.path} className="space-y-1">
              <Label htmlFor={`gw-test-${fieldKey(f)}`} size="sm">{f.label}</Label>
              <Input id={`gw-test-${fieldKey(f)}`} value={values[fieldKey(f)] ?? ''} onChange={(e) => setValues((v) => ({ ...v, [fieldKey(f)]: e.target.value }))} data-testid={`flow-step-test-gateway-field-${fieldKey(f)}`} />
            </div>
          ))}
          <Button type="button" size="sm" onClick={useEdited} data-testid="flow-step-test-gateway-use">Use this message</Button>
        </div>
      )}
      {note && <p role="status" className="text-xs text-muted-foreground" data-testid="flow-step-test-trigger-note">{note}</p>}
    </div>
  );
}
