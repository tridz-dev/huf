import { useEffect, useState } from 'react';
import { Copy, RefreshCw } from 'lucide-react';
import { Button } from '../../ui/button';
import { FieldHint } from '../FieldHint';
import { FlowTriggerPanel } from '../../FlowTriggerPanel';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { WEBHOOK_RESPONSES } from '@/lib/flow/flowHelp';
import { copyText } from '@/lib/clipboard';
import { generateWebhookSecret, webhookUrl, webhookUsage } from '@/lib/flow-graph/flowWebhookUi';
import { getTriggerDoctypes } from '../../../services/flowApi';
import { toast } from '@/lib/toast';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { type Opt, Section, str, tid, useNodeForm } from './formKit';

export function TriggerConfigForm({ nodeId }: { nodeId: string }) {
  const { node, cfg, patch, kind, shell, activeFlow } = useNodeForm(nodeId, 'triggerConfig');
  const { canManage } = useFlowPermissions();
  const [docTypes, setDocTypes] = useState<Opt[]>([]);
  const [loadingDocTypes, setLoadingDocTypes] = useState(false);
  const type = str(cfg.type);

  useEffect(() => {
    if (type !== 'doc-event' || docTypes.length) return;
    setLoadingDocTypes(true);
    getTriggerDoctypes()
      .then((l) => setDocTypes((l || []).map((d: { name: string }) => ({ value: d.name, label: d.name }))))
      .catch(() => setDocTypes([]))
      .finally(() => setLoadingDocTypes(false));
  }, [type, docTypes.length]);

  if (!node) return null;

  if (type === 'webhook') {
    const secret = str(cfg.secret);
    // The server hides the secret from people who cannot edit the flow; they are never offered a way to copy or change it.
    const secretHidden = !canManage || cfg.secret_hidden === true;
    const method = str(cfg.method) || 'POST';
    const origin = window.location.origin;
    const usage = webhookUsage(origin, activeFlow?.id, secretHidden ? undefined : secret, method);
    const copy = async (text: string, what: string) => {
      if (await copyText(text)) toast.success(`${what} copied`);
      else toast.error("Couldn't copy. Select the text and copy it yourself.");
    };
    return (
      <Section title="Webhook" hint="Starts the flow when another system sends a request to the address below. The flow must be published first. The data it sends becomes the flow input, which steps read as input['name'].">
        <div>
          <Label size="sm">Webhook URL</Label>
          <div className="flex gap-2 mt-1">
            <Input
              readOnly
              aria-label="Webhook URL"
              value={webhookUrl(origin, activeFlow?.id)}
              data-testid={tid(kind, 'url')}
              className="bg-muted/50 font-mono text-xs text-muted-foreground"
            />
            <Button variant="outline" size="icon" aria-label="Copy webhook URL" data-testid="flow-webhook-copy-url" onClick={() => copy(webhookUrl(origin, activeFlow?.id), 'Webhook URL')}>
              <Copy className="w-3.5 h-3.5" />
            </Button>
          </div>
          <FieldHint testId="flow-hint-webhook-url">Give this address to the system that should start the flow.</FieldHint>
        </div>
        {secretHidden ? (
          <div>
            <Label size="sm">Secret</Label>
            <p
              className="mt-1 rounded-md border border-dashed border-line bg-muted/40 px-2.5 py-2 text-xs text-muted-foreground"
              data-testid="flow-webhook-secret-hidden"
            >
              Hidden. Only people who can edit this flow see the secret.
            </p>
          </div>
        ) : (
          <div>
            <Label htmlFor="webhook-secret" size="sm">Secret</Label>
            <div className="flex gap-2 mt-1">
              <Input
                id="webhook-secret"
                data-testid={tid(kind, 'secret')}
                value={secret}
                onChange={(e) => patch({ secret: e.target.value })}
                className="font-mono text-xs"
              />
              <Button variant="outline" size="icon" aria-label="Copy secret" data-testid="flow-webhook-copy-secret" disabled={!secret} onClick={() => copy(secret, 'Secret')}>
                <Copy className="w-3.5 h-3.5" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                aria-label="Generate a new secret"
                data-testid="flow-webhook-regenerate"
                onClick={() => {
                  patch({ secret: generateWebhookSecret() });
                  toast.info('New secret generated. Save the flow, then update anything that calls this webhook.');
                }}
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </Button>
            </div>
            <FieldHint testId="flow-hint-webhook-secret">A password only your callers know. They send it in the X-Huf-Secret header. Generate a new one if it leaks.</FieldHint>
            <shell.Err field="secret" />
          </div>
        )}
        <div>
          <Label htmlFor="webhook-method" size="sm">Method</Label>
          <Select value={method} onValueChange={(v) => patch({ method: v })}>
            <SelectTrigger id="webhook-method" data-testid={tid(kind, 'method')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="GET" data-testid="flow-option-webhook-method-GET">GET</SelectItem>
              <SelectItem value="POST" data-testid="flow-option-webhook-method-POST">POST</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint testId="flow-hint-webhook-method">Callers must use this method. POST can carry data as JSON; GET cannot.</FieldHint>
          <shell.Err field="method" />
        </div>
        <div className="text-xs space-y-1" data-testid="flow-webhook-usage">
          <p className="font-medium">How to call it</p>
          <p className="text-muted-foreground">Send the secret as a header (not in the address):</p>
          <code className="block break-all rounded bg-muted/50 p-1.5 font-mono text-eyebrow tracking-normal" data-testid="flow-webhook-usage-header">{usage.header}</code>
          <p className="text-muted-foreground">Example:</p>
          <code className="block break-all rounded bg-muted/50 p-1.5 font-mono text-eyebrow tracking-normal" data-testid="flow-webhook-usage-curl">{usage.curl}</code>
          {method === 'POST' && (
            <>
              <p className="text-muted-foreground">To send data as well:</p>
              <code className="block break-all rounded bg-muted/50 p-1.5 font-mono text-eyebrow tracking-normal" data-testid="flow-webhook-usage-curl-data">{usage.curlWithData}</code>
            </>
          )}
          <p className="text-muted-foreground">What you get back:</p>
          <ul className="space-y-0.5 text-muted-foreground" data-testid="flow-webhook-responses">
            {WEBHOOK_RESPONSES.map((r) => (
              <li key={r.code}><span className="font-mono">{r.code}</span> {r.meaning}</li>
            ))}
          </ul>
        </div>
      </Section>
    );
  }

  if (type === 'schedule' || type === 'doc-event') {
    return (
      <Section title={type === 'schedule' ? 'Schedule' : 'Data'}>
        <FlowTriggerPanel
          kind={type}
          docTypes={docTypes}
          loadingDocTypes={loadingDocTypes}
          value={{ cron: str(cfg.cron), doctype: str(cfg.doctype), event: str(cfg.event) }}
          onChange={patch}
          errors={{ cron: shell.error('cron'), doctype: shell.error('doctype'), event: shell.error('event') }}
        />
      </Section>
    );
  }
  return null;
}
