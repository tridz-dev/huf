import { useEffect, useMemo, useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import { Dialog, DialogDescription, DialogTitle } from '../ui/dialog';
import { DialogScrollBody, DialogScrollContent, DialogScrollFooter, DialogScrollHeader } from '../ui/dialog-scroll';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { RadioGroup, RadioGroupItem } from '../ui/radio-group';
import { Switch } from '../ui/switch';
import { JsonArea } from '../common/JsonArea';
import { cn } from '@/lib/utils';
import { withShortcut } from './shortcuts/shortcutHints';
import { getFlowDefinition } from '@/services/flowApi';
import { getLastWebhookRequest } from '@/services/flow/triggerApi';
import { parsePayload, readLastPayload, rememberPayload, RUN_MODE_BUTTON, type RunMode } from '@/lib/flow-run/flowRunPayload';
import { hasData, payloadFromForm, runFormFields, valuesFromPayload, type RunField, type RunFormValues } from '@/lib/flow-run/runForm';

interface RunFlowDialogProps {
  open: boolean;
  flowId: string | null;
  flowName?: string;
  onOpenChange: (open: boolean) => void;
  /** Starts the run with the parsed payload and the chosen mode. Resolve when the run has been reported. */
  onRun: (payload: Record<string, unknown>, mode: RunMode) => Promise<void>;
}

interface FlowInputs {
  fields: RunField[];
  sample: Record<string, unknown> | null;
  isWebhook: boolean;
}

const NO_INPUTS: FlowInputs = { fields: [], sample: null, isWebhook: false };
const pretty = (value: unknown) => JSON.stringify(value, null, 2);

const MODES: Array<{ value: RunMode; title: string; text: string }> = [
  {
    value: 'test',
    title: 'Test run (nothing is sent)',
    text: 'Looks things up for real. Emails, messages and changes to your records are skipped, and each one shows what it would have done.',
  },
  {
    value: 'real',
    title: 'Run for real',
    text: 'Does everything the flow says, including sending emails and messages and changing records.',
  },
];

/** Reads what the flow's trigger says it will receive: the fields it declares, else its saved sample request. */
async function loadInputs(flowId: string): Promise<FlowInputs> {
  const doc = await getFlowDefinition(flowId);
  const graph = doc.definition_json as unknown as { nodes?: Array<Record<string, unknown>>; contract?: { input_schema?: unknown } };
  const triggers = (graph.nodes ?? []).filter((n) => typeof n.type === 'string' && (n.type as string).startsWith('trigger.'));
  const withSample = triggers.find((n) => n._sample && typeof n._sample === 'object');
  const sample = (withSample?._sample as Record<string, unknown> | undefined) ?? null;
  return {
    fields: runFormFields(graph.contract?.input_schema, sample),
    sample,
    isWebhook: triggers.some((n) => n.type === 'trigger.webhook'),
  };
}

export function RunFlowDialog({ open, flowId, flowName, onOpenChange, onRun }: RunFlowDialogProps) {
  const [mode, setMode] = useState<RunMode>('test');
  const [inputs, setInputs] = useState<FlowInputs>(NO_INPUTS);
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState('{}');
  const [values, setValues] = useState<RunFormValues>({});
  const [note, setNote] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!open || !flowId) return;
    let cancelled = false;
    setMode('test');
    setNote(null);
    setLoading(true);
    const remembered = parsePayload(readLastPayload(flowId)).value;
    setText(readLastPayload(flowId));
    setValues({});
    loadInputs(flowId)
      .catch(() => NO_INPUTS)
      .then((found) => {
        if (cancelled) return;
        setInputs(found);
        const start = hasData(remembered) ? remembered : found.sample ?? {};
        setValues(valuesFromPayload(found.fields, start));
        setText(hasData(start) ? pretty(start) : '{}');
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, flowId]);

  const parsed = useMemo(() => parsePayload(text), [text]);
  const error = parsed.error;
  const hasForm = inputs.fields.length > 0;

  const applyPayload = (payload: Record<string, unknown>) => {
    setText(hasData(payload) ? pretty(payload) : '{}');
    setValues(valuesFromPayload(inputs.fields, payload));
  };

  const editBox = (field: RunField, value: string | boolean) => {
    const next = { ...values, [field.id]: value };
    setValues(next);
    setText(pretty(payloadFromForm(parsed.value ?? {}, inputs.fields, next)));
  };

  const editJson = (next: string) => {
    setText(next);
    const result = parsePayload(next);
    if (result.value) setValues(valuesFromPayload(inputs.fields, result.value));
  };

  const useLastRequest = async () => {
    if (!flowId) return;
    setNote(null);
    try {
      const last = await getLastWebhookRequest(flowId);
      if (last.found && last.sample) {
        applyPayload(last.sample);
        setNote('Filled in with the last request this flow received.');
      } else {
        setNote('This flow has not received a request yet.');
      }
    } catch {
      setNote('Could not load the last request. Only people who can edit the flow can use it.');
    }
  };

  const useSample = () => {
    if (!inputs.sample) return;
    setNote(null);
    applyPayload(inputs.sample);
  };

  const handleRun = async () => {
    if (!flowId) return;
    if (parsed.error || !parsed.value) return;
    setRunning(true);
    try {
      rememberPayload(flowId, text);
      await onRun(parsed.value, mode);
      onOpenChange(false);
    } finally {
      setRunning(false);
    }
  };

  const formView = (
    <div className="grid gap-3" data-testid="flow-run-form">
      {inputs.fields.map((field) => {
        const id = `flow-run-field-${field.id.replace(/[^a-z0-9]+/gi, '-')}`;
        const value = values[field.id];
        return (
          <div key={field.id} className="grid gap-1">
            {field.kind === 'yesno' ? (
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor={id}>{field.label}</Label>
                <Switch id={id} checked={value === true} onCheckedChange={(on) => editBox(field, on)} data-testid={id} />
              </div>
            ) : (
              <>
                <Label htmlFor={id}>{field.label}</Label>
                {field.kind === 'longtext' ? (
                  <Textarea id={id} rows={3} value={String(value ?? '')} onChange={(e) => editBox(field, e.target.value)} data-testid={id} />
                ) : (
                  <Input
                    id={id}
                    inputMode={field.kind === 'number' ? 'decimal' : undefined}
                    value={String(value ?? '')}
                    onChange={(e) => editBox(field, e.target.value)}
                    data-testid={id}
                  />
                )}
              </>
            )}
          </div>
        );
      })}
    </div>
  );

  const jsonHelp = (
    <>
      The data the trigger would hand to the flow, as text. Steps read it as input, for example {'{"name": "Ada"}'} makes input.name available.
      Leave it as {'{}'} to run without input.
    </>
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !running && onOpenChange(next)}>
      <DialogScrollContent
        className="sm:max-w-[560px]"
        data-testid="flow-run-dialog"
        // Cmd/Ctrl+Enter again starts the test run (never a real one: that one is a click on purpose).
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && mode === 'test' && !running && !loading && !error) {
            e.preventDefault();
            void handleRun();
          }
        }}
      >
        <DialogScrollHeader>
          <DialogTitle>Run {flowName ? `"${flowName}"` : 'flow'}</DialogTitle>
          <DialogDescription>Starts the flow once, right now, as if its trigger had fired. Choose how, then give it the details it would receive.</DialogDescription>
        </DialogScrollHeader>
        <DialogScrollBody className="grid gap-4 py-4">
          <RadioGroup value={mode} onValueChange={(v) => setMode(v as RunMode)} className="gap-2" aria-label="How to run" data-testid="flow-run-mode">
            {MODES.map((m) => (
              <Label
                key={m.value}
                htmlFor={`flow-run-mode-${m.value}`}
                className={cn(
                  'flex cursor-pointer items-start gap-3 rounded-md border p-3 font-normal',
                  mode === m.value ? (m.value === 'real' ? 'border-warning bg-warning-tint' : 'border-primary bg-muted/40') : 'border-line',
                )}
                data-testid={`flow-run-mode-${m.value}-card`}
              >
                <RadioGroupItem id={`flow-run-mode-${m.value}`} value={m.value} className="mt-0.5" data-testid={`flow-run-mode-${m.value}`} />
                <span className="grid gap-0.5">
                  <span className="text-sm font-medium">{m.title}</span>
                  <span className="text-meta text-muted-foreground">{m.text}</span>
                </span>
              </Label>
            ))}
          </RadioGroup>

          {mode === 'real' && (
            <p role="note" className="rounded-md bg-warning-tint px-3 py-2 text-sm text-warning" data-testid="flow-run-real-warning">
              This is a real run: emails and messages go out and records are created or changed. If you only want to see what would happen, choose Test run.
            </p>
          )}

          <div className="grid gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="mr-auto text-sm font-medium">{hasForm ? 'Details' : 'Input data'}</h3>
              {inputs.isWebhook && (
                <Button type="button" variant="outline" size="sm" onClick={useLastRequest} disabled={loading} data-testid="flow-run-use-last">
                  Use last real request
                </Button>
              )}
              {inputs.sample && (
                <Button type="button" variant="outline" size="sm" onClick={useSample} disabled={loading} data-testid="flow-run-use-sample">
                  Use sample
                </Button>
              )}
            </div>
            {note && (
              <p role="status" className="text-meta text-muted-foreground" data-testid="flow-run-note">
                {note}
              </p>
            )}
            {loading ? (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground" data-testid="flow-run-loading">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Loading the details this flow expects…
              </div>
            ) : (
              <JsonArea
                surfaceKey="run-payload"
                title={hasForm ? 'Details as JSON' : 'Input data (JSON)'}
                help={hasForm ? 'The same details as text, for people who work with JSON. Changing one changes the other.' : jsonHelp}
                value={text}
                onChange={editJson}
                formView={hasForm ? formView : undefined}
              />
            )}
            {!hasForm && !loading && !error && (
              <p className="text-meta text-muted-foreground" data-testid="flow-run-payload-hint">
                This flow does not say what details it expects. Leave the box as {'{}'} to run without any. When the run finishes, find it under Runs.
              </p>
            )}
          </div>
        </DialogScrollBody>
        <DialogScrollFooter>
          <Button variant="outline" size="sm" data-testid="flow-run-cancel" onClick={() => onOpenChange(false)} disabled={running}>
            Cancel
          </Button>
          <Button size="sm" className="gap-2" data-testid="flow-run-start" title={mode === 'test' ? withShortcut('Start the test run', 'flow-run') : undefined} onClick={handleRun} disabled={running || loading || !!error}>
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {RUN_MODE_BUTTON[mode]}
          </Button>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
