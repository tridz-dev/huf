import { useEffect, useMemo, useState } from 'react';
import { ChevronRight, Copy, Eye, EyeOff, RefreshCw } from 'lucide-react';
import { Button } from '../../ui/button';
import { FieldHint } from '../FieldHint';
import { CodeBlock } from '../CodeBlock';
import { JsonArea } from '../../common/JsonArea';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { Textarea } from '../../ui/textarea';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../../ui/alert-dialog';
import { StatusPill } from '../../common/StatusPill';
import { WEBHOOK_RESPONSES } from '@/lib/flow/flowHelp';
import { copyText } from '@/lib/clipboard';
import { SECRET_REVEAL_MS, generateWebhookSecret, maskSecret, webhookUrl, webhookUsage } from '@/lib/flow-graph/flowWebhookUi';
import { EXAMPLE_REQUEST, inferFields, parseSampleText, redactSample } from '@/lib/flow-trigger/sample';
import { getLastWebhookRequest } from '@/services/flow/triggerApi';
import { toast } from '@/lib/toast';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { str, tid, useNodeForm } from './formKit';
import { type FlowNodeData } from '@/types/flow.types';

const pretty = (v: unknown) => JSON.stringify(v, null, 2);

/** Setup first (how it is called, the secret, the address), then the data it sends, then the developer reference. */
export function WebhookTriggerForm({ nodeId }: { nodeId: string }) {
  const { node, cfg, patch, kind, activeFlow } = useNodeForm(nodeId, 'triggerConfig');
  const { updateNodeData } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const secret = str(cfg.secret);
  // The server hides the secret from people who cannot edit the flow; they are never offered a way to copy or change it.
  const secretHidden = !canManage || cfg.secret_hidden === true;
  const method = str(cfg.method) || 'POST';
  const origin = window.location.origin;
  const url = webhookUrl(origin, activeFlow?.id);
  const live = activeFlow?.status === 'active';

  // Show for 30 seconds, then hide again.
  const [revealed, setRevealed] = useState(false);
  const [confirmNew, setConfirmNew] = useState(false);
  const [freshSecret, setFreshSecret] = useState(false);
  useEffect(() => {
    if (!revealed) return;
    const t = setTimeout(() => setRevealed(false), SECRET_REVEAL_MS);
    return () => clearTimeout(t);
  }, [revealed]);

  const copy = async (text: string, what: string) => {
    if (await copyText(text)) toast.success(`${what} copied`);
    else toast.error("Couldn't copy. Select the text and copy it yourself.");
  };

  const sample = node?.data.sample;
  const setSample = (next: Record<string, unknown> | undefined) =>
    updateNodeData(nodeId, (data) => {
      const rest = { ...data } as FlowNodeData;
      if (next === undefined) delete rest.sample;
      else rest.sample = next;
      return rest;
    });

  return (
    <div className="space-y-4" data-testid="flow-webhook-panel">
      <p className="text-xs text-muted-foreground" data-testid="flow-hint-webhook-intro">
        Starts the flow when another app or website sends a request to the address below. It only works while the flow is live. Anything it sends can be used by the steps that follow.
      </p>

      <div>
        <Label htmlFor="webhook-method" size="sm">How it is called</Label>
        <Select value={method} disabled={!canManage} onValueChange={(v) => patch({ method: v })}>
          <SelectTrigger id="webhook-method" data-testid={tid(kind, 'method')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="POST" data-testid="flow-option-webhook-method-POST">POST (can send data)</SelectItem>
            <SelectItem value="GET" data-testid="flow-option-webhook-method-GET">GET (just a ping)</SelectItem>
          </SelectContent>
        </Select>
        <FieldHint testId="flow-hint-webhook-method">
          POST lets the other app send data along (recommended). GET only starts the flow; no data can be sent.
        </FieldHint>
      </div>

      {secretHidden ? (
        <div>
          <Label size="sm">Secret</Label>
          <p
            className="mt-1 rounded-md border border-dashed border-line bg-muted/40 px-2.5 py-2 text-xs text-muted-foreground"
            data-testid="flow-webhook-secret-hidden"
          >
            Hidden. Ask a flow editor.
          </p>
        </div>
      ) : (
        <div>
          <Label htmlFor="webhook-secret" size="sm">Secret</Label>
          <div className="mt-1 flex items-center gap-2">
            <Input
              id="webhook-secret"
              readOnly
              data-testid={tid(kind, 'secret')}
              data-masked={revealed ? 'false' : 'true'}
              value={revealed ? secret : maskSecret(secret)}
              onFocus={(e) => e.currentTarget.select()}
              className="min-w-0 flex-1 bg-muted/50 font-mono text-xs"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!secret}
              aria-label={revealed ? 'Hide secret' : 'Show secret for 30 seconds'}
              data-testid="flow-webhook-secret-toggle"
              onClick={() => setRevealed((v) => !v)}
            >
              {revealed ? <EyeOff className="mr-1 h-3.5 w-3.5" /> : <Eye className="mr-1 h-3.5 w-3.5" />}
              {revealed ? 'Hide' : 'Show'}
            </Button>
            <Button type="button" variant="outline" size="icon" aria-label="Copy secret" disabled={!secret} data-testid="flow-webhook-copy-secret" onClick={() => copy(secret, 'Secret')}>
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </div>
          <FieldHint testId="flow-hint-webhook-secret">
            A password only the apps that call this flow know. They send it with every request.{revealed ? ' It hides itself again in 30 seconds.' : ''}
          </FieldHint>
          <Button type="button" variant="ghost" size="sm" className="mt-1 px-2 text-xs" data-testid="flow-webhook-regenerate" onClick={() => setConfirmNew(true)}>
            <RefreshCw className="mr-1 h-3 w-3" />
            Make a new secret
          </Button>
          {freshSecret && (
            <p role="status" className="mt-1 text-meta text-signal-ink" data-testid="flow-webhook-secret-new-note">
              New secret made. Save the flow, then give it to every app that calls this one.
            </p>
          )}
        </div>
      )}

      <div>
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor="webhook-url" size="sm">Web address</Label>
          <StatusPill kind={live ? 'live' : 'draft'} label={live ? 'Live' : 'Not live yet'} data-testid="flow-webhook-live" />
        </div>
        <div className="mt-1 flex items-start gap-2">
          <Textarea
            id="webhook-url"
            readOnly
            rows={2}
            aria-label="Webhook URL"
            value={url}
            data-testid={tid(kind, 'url')}
            onFocus={(e) => e.currentTarget.select()}
            className="min-h-0 flex-1 resize-none break-all bg-muted/50 font-mono text-xs text-muted-foreground"
          />
          <Button type="button" variant="outline" size="sm" data-testid="flow-webhook-copy-url" onClick={() => copy(url, 'Web address')}>
            <Copy className="mr-1 h-3.5 w-3.5" />
            Copy
          </Button>
        </div>
        <FieldHint testId="flow-hint-webhook-url">Give this address to the app that should start the flow.{live ? '' : ' Publish the flow to switch it on.'}</FieldHint>
      </div>

      {method === 'POST' && <SampleSection nodeId={nodeId} sample={sample} canEdit={canManage} flowId={activeFlow?.id} onSample={setSample} />}

      <HowToCall
        method={method}
        origin={origin}
        flowId={activeFlow?.id}
        secret={revealed && !secretHidden ? secret : undefined}
        sample={sample}
      />

      <AlertDialog open={confirmNew} onOpenChange={setConfirmNew}>
        <AlertDialogContent data-testid="flow-webhook-regenerate-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Make a new secret?</AlertDialogTitle>
            <AlertDialogDescription>
              Anything that calls this flow with the old secret will stop working until you give it the new one.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="flow-webhook-regenerate-cancel">Keep the old one</AlertDialogCancel>
            <AlertDialogAction
              data-testid="flow-webhook-regenerate-confirm"
              onClick={() => {
                patch({ secret: generateWebhookSecret() });
                setFreshSecret(true);
                setRevealed(true);
              }}
            >
              Make a new secret
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/** "Data it sends": the fields of a sample request, with ways to paste one or take the last real one. */
function SampleSection({ nodeId, sample, canEdit, flowId, onSample }: {
  nodeId: string;
  sample: Record<string, unknown> | undefined;
  canEdit: boolean;
  flowId: string | undefined;
  onSample: (next: Record<string, unknown> | undefined) => void;
}) {
  const [pasting, setPasting] = useState(false);
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const fields = useMemo(() => inferFields(sample), [sample]);
  const problem = text.trim() !== '' && parseSampleText(text) === null;

  const startPaste = () => {
    setText(pretty(sample ?? EXAMPLE_REQUEST));
    setNote(null);
    setPasting(true);
  };
  const save = () => {
    const parsed = parseSampleText(text);
    if (!parsed) return;
    onSample(redactSample(parsed) as Record<string, unknown>);
    setPasting(false);
    setNote('Saved. Later steps can use these fields.');
  };
  const useLast = async () => {
    if (!flowId) return;
    setLoading(true);
    setNote(null);
    try {
      const last = await getLastWebhookRequest(flowId);
      if (last.found && last.sample) {
        onSample(last.sample);
        setNote('Took the last request this webhook received.');
      } else {
        setNote('Nothing has called this webhook yet. Paste a sample instead.');
      }
    } catch {
      setNote("Couldn't load the last request. Paste a sample instead.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="flow-webhook-data" data-node={nodeId}>
      <Label size="sm">Data it sends</Label>
      {fields.length > 0 ? (
        <ul className="mt-1 divide-y divide-line rounded-md border border-line text-xs" data-testid="flow-webhook-fields">
          {fields.map((f) => (
            <li key={f.label} className="flex items-baseline justify-between gap-3 px-2.5 py-1.5" data-testid="flow-webhook-field">
              <span className="min-w-0 break-words font-medium text-ink">{f.label}</span>
              <span className="min-w-0 break-words text-right text-muted-foreground">{f.example}</span>
            </li>
          ))}
        </ul>
      ) : (
        <FieldHint testId="flow-webhook-no-sample">
          Nothing yet. Paste a sample request, or use the last one this webhook received, to see the fields your steps can use.
        </FieldHint>
      )}
      {canEdit && !pasting && (
        <div className="mt-2 flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" data-testid="flow-webhook-paste-sample" onClick={startPaste}>
            Paste a sample request
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={loading || !flowId} data-testid="flow-webhook-use-last" onClick={useLast}>
            {loading ? 'Looking...' : 'Use last received request'}
          </Button>
          {sample && (
            <Button type="button" variant="ghost" size="sm" data-testid="flow-webhook-clear-sample" onClick={() => onSample(undefined)}>
              Clear
            </Button>
          )}
        </div>
      )}
      {note && <p role="status" className="mt-1 text-meta text-muted-foreground" data-testid="flow-webhook-sample-note">{note}</p>}
      {pasting && (
        <div className="mt-2 space-y-2">
          <JsonArea
            surfaceKey="webhook-sample"
            title="Sample request (JSON)"
            help="Paste what the other app sends, or change this example. Only the field names and example values are kept (passwords and keys are hidden, long text is shortened). If it is not valid JSON you will be told where, and it will not be saved."
            value={text}
            onChange={setText}
            allowEmpty={false}
          />
          <div className="flex gap-2">
            <Button type="button" size="sm" disabled={problem || text.trim() === ''} data-testid="flow-webhook-sample-save" onClick={save}>
              Save sample
            </Button>
            <Button type="button" variant="ghost" size="sm" data-testid="flow-webhook-sample-cancel" onClick={() => setPasting(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** The developer reference, folded away: example command, request body, and what comes back. */
function HowToCall({ method, origin, flowId, secret, sample }: {
  method: string;
  origin: string;
  flowId: string | undefined;
  secret: string | undefined;
  sample: Record<string, unknown> | undefined;
}) {
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState(() => pretty(sample ?? EXAMPLE_REQUEST));
  // A new saved sample becomes the example body.
  const sampleText = pretty(sample ?? EXAMPLE_REQUEST);
  useEffect(() => setBody(sampleText), [sampleText]);
  const usage = webhookUsage(origin, flowId, secret, method, method === 'POST' ? body : undefined);
  return (
    <div className="rounded-md border border-line" data-testid="flow-webhook-usage" data-open={open}>
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-sm font-medium"
        data-testid="flow-webhook-howto-toggle"
        onClick={() => setOpen((v) => !v)}
      >
        <ChevronRight className={`h-4 w-4 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`} aria-hidden />
        How to call this webhook
      </button>
      {open && (
        <div className="space-y-3 border-t border-line p-3" data-testid="flow-webhook-howto">
          <p className="text-xs text-muted-foreground">
            For whoever connects the other app. Send the secret in a header called X-Huf-Secret (never in the address), using the method you chose above.
          </p>
          {method === 'POST' && (
            <JsonArea
              surfaceKey="webhook-body"
              title="Request body (JSON)"
              help="The data the other app sends with its request. This is an example; change it to match what your app really sends. It only changes the command below. If it is not valid JSON the command shows your text unchanged."
              value={body}
              onChange={setBody}
            />
          )}
          <CodeBlock title="Example command" text={usage.curl} testId="flow-webhook-usage-curl" />
          {secret === undefined && (
            <p className="text-meta text-muted-foreground" data-testid="flow-webhook-usage-secret-note">
              The command shows a placeholder for the secret. Press Show above to put the real one in.
            </p>
          )}
          <div className="text-xs">
            <p className="font-medium">What you get back</p>
            <ul className="mt-1 space-y-0.5 text-muted-foreground" data-testid="flow-webhook-responses">
              {WEBHOOK_RESPONSES.map((r) => (
                <li key={r.code}><span className="font-mono">{r.code}</span> {r.meaning}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
