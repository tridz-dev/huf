import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { toast } from '@/lib/toast';
import { Copy, RefreshCw } from 'lucide-react';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Combobox } from '../ui/combobox';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '../ui/select';
import { VariablePicker } from '../ui/VariablePicker';
import { FlowValueInput } from '../FlowValueInput';
import { FlowTriggerPanel } from '../FlowTriggerPanel';
import { useFlowContext } from '../../contexts/FlowContext';
import { getAgents } from '../../services/agentApi';
import { getApproverRoles, getTriggerDoctypes } from '../../services/flowApi';
import { getFlowTools, type FlowTool } from '../../services/toolApi';
import { getModels, getProviders } from '../../services/providerApi';
import { isChatModel } from '@/lib/chatModel';
import { NotConnected } from './NotConnected';
import { SlackChannelPicker } from './SlackChannelPicker';
import { ACTION_CARD_CONTRACT } from '../../data/actions';
import { registerToolSchemas } from '@/lib/flowToolSchemas';
import { TRANSFORM_OPS, getTransformOp } from '@/lib/flowTransformOps';
import { branchHandlesFor } from '@/lib/flowBranches';
import { validateNode, TOOL_REQUIRED_INPUT, nodeKind } from '@/lib/flowValidation';
import { generateWebhookSecret, webhookUrl, webhookUsage } from '@/lib/flowWebhookUi';
import { actionCardId, actionLabel } from '@/lib/flowLabels';
import { copyText } from '@/lib/clipboard';
import { toolLabel } from '@/lib/flowIntegrations';
import { uniqueName } from '@/lib/flowRefs';
import { linkRoutes } from '@/lib/link-routes';
import { edgeRoute } from '../../services/flowSerializer';
import type { FlowNodeData } from '../../types/flow.types';

type Cfg = Record<string, unknown>;
type Opt = { value: string; label: string };

const asObj = (v: unknown): Cfg => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Cfg) : {});
const str = (v: unknown): string => (typeof v === 'string' ? v : '');

interface FormShell {
  kind: string;
  error: (field: string) => string | undefined;
  /** Required-field message under a control. */
  Err: (props: { field: string }) => ReactNode;
}

/** How long typing may pause before an edit is written to the flow. Keeps a fast typist from re-rendering the whole canvas on every key. */
const COMMIT_DELAY_MS = 200;

/**
 * Shared hook: current node, its config, a merge-patch writer and the inline-error helper.
 * Edits show up in the form at once (local draft) and reach the flow after a short pause, on blur and on unmount.
 */
function useNodeForm(nodeId: string, slot: 'triggerConfig' | 'actionConfig') {
  const { activeFlow, updateNodeData, getNode } = useFlowContext();
  const node = activeFlow?.nodes.find((n) => n.id === nodeId);
  const edges = activeFlow?.edges ?? [];
  const draftRef = useRef<{ nodeId: string; cfg: Cfg } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [, rerender] = useState(0);

  const commit = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const draft = draftRef.current;
    if (!draft) return;
    draftRef.current = null;
    updateNodeData(draft.nodeId, (data) => ({ ...data, [slot]: draft.cfg }) as FlowNodeData);
  }, [updateNodeData, slot]);

  // Write any pending edit when focus leaves a field (so Save/Run right after typing see it) and when this form goes away.
  useEffect(() => {
    document.addEventListener('focusout', commit);
    return () => {
      document.removeEventListener('focusout', commit);
      commit();
    };
  }, [commit, nodeId]);

  const draft = draftRef.current && draftRef.current.nodeId === nodeId ? draftRef.current.cfg : null;
  const cfg = draft ?? asObj(node?.data[slot]);

  const patch = (p: Cfg) => {
    const base = draftRef.current && draftRef.current.nodeId === nodeId ? draftRef.current.cfg : asObj(getNode(nodeId)?.data[slot]);
    if (!getNode(nodeId)) return;
    const merged: Cfg = { ...base, ...p };
    for (const k of Object.keys(p)) if (p[k] === undefined) delete merged[k];
    draftRef.current = { nodeId, cfg: merged };
    rerender((n) => n + 1);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(commit, COMMIT_DELAY_MS);
  };

  const kind = node ? nodeKind(node) : 'unknown';
  const issues = node ? validateNode(node, edges) : [];
  const error = (field: string) => issues.find((i) => i.field === field)?.message;
  const Err = ({ field }: { field: string }) => {
    const m = error(field);
    return m ? (
      <p role="alert" className="mt-1 text-[11px] text-destructive" data-testid={`flow-error-${kind}-${field}`}>
        {m}
      </p>
    ) : null;
  };
  const shell: FormShell = { kind, error, Err };
  return { node, edges, cfg, patch, kind, shell, activeFlow };
}

const tid = (kind: string, field: string) => `flow-field-${kind}-${field}`;

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-3">
      <Label weight="semibold" className="mb-2 block" data-testid="flow-config-title">
        {title}
      </Label>
      {hint ? <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md">{hint}</div> : null}
      {children}
    </div>
  );
}

/**
 * A multi-line text field with an "Insert data" picker that inserts the chosen reference text at the cursor.
 * `format` turns the reference path into the text to insert (an expression name, or a `{placeholder}`).
 */
function PickerTextarea({
  id, testId, pickerTestId, nodeId, label, value, onChange, format, placeholder, className, mono,
}: {
  id: string;
  testId: string;
  pickerTestId: string;
  nodeId: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  format: (ref: string) => string;
  placeholder?: string;
  className?: string;
  mono?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const insert = (reference: string) => {
    const text = format(reference);
    const el = ref.current;
    const at = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? at;
    onChange(`${value.slice(0, at)}${text}${value.slice(end)}`);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(at + text.length, at + text.length);
    });
  };
  return (
    <div>
      <div className="flex justify-between items-center mb-1 min-h-7">
        <Label htmlFor={id} size="sm">{label}</Label>
        <VariablePicker currentNodeId={nodeId} testId={pickerTestId} label={`Insert data into ${label}`} onSelect={(r) => insert(r)} />
      </div>
      <Textarea
        id={id}
        ref={ref}
        data-testid={testId}
        className={`${className ?? 'min-h-[80px]'} w-full${mono ? ' font-mono' : ''}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}

// ─── Triggers ─────────────────────────────────────────────────────────

export function TriggerConfigForm({ nodeId }: { nodeId: string }) {
  const { node, cfg, patch, kind, shell, activeFlow } = useNodeForm(nodeId, 'triggerConfig');
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
    const method = str(cfg.method) || 'POST';
    const origin = window.location.origin;
    const usage = webhookUsage(origin, activeFlow?.id, secret, method);
    const copy = async (text: string, what: string) => {
      if (await copyText(text)) toast.success(`${what} copied`);
      else toast.error("Couldn't copy. Select the text and copy it yourself.");
    };
    return (
      <Section title="Webhook" hint="Send a request to this address to start the flow. Callers must send the secret in the X-Huf-Secret header.">
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
        </div>
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
          <shell.Err field="secret" />
        </div>
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
          <shell.Err field="method" />
        </div>
        <div className="text-xs space-y-1" data-testid="flow-webhook-usage">
          <p className="font-medium">How to call it</p>
          <p className="text-muted-foreground">Send the secret as a header (not in the address):</p>
          <code className="block break-all rounded bg-muted/50 p-1.5 font-mono text-[10px]" data-testid="flow-webhook-usage-header">{usage.header}</code>
          <p className="text-muted-foreground">Example:</p>
          <code className="block break-all rounded bg-muted/50 p-1.5 font-mono text-[10px]" data-testid="flow-webhook-usage-curl">{usage.curl}</code>
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

// ─── Actions ──────────────────────────────────────────────────────────

/** Fallback `input` keys per preset tool, used until/unless the tool's own schema is loaded. */
const PRESET_FIELDS: Record<string, Array<{ key: string; label: string; optional?: boolean; placeholder?: string; hint?: string }>> = {
  gmail_send_email: [
    { key: 'to', label: 'To', placeholder: 'name@example.com', hint: 'One address, or several separated by commas.' },
    { key: 'subject', label: 'Subject' },
    { key: 'body', label: 'Body' },
  ],
  slack_send_message: [
    { key: 'channel', label: 'Channel', placeholder: '#general', hint: 'The channel name (like #general) or the channel ID. The bot must be invited to it.' },
    { key: 'text', label: 'Message' },
  ],
  slack_send_thread_reply: [
    { key: 'channel', label: 'Channel', placeholder: '#general', hint: 'The channel name (like #general) or the channel ID. The bot must be invited to it.' },
    { key: 'thread_ts', label: 'Thread', placeholder: '1712345678.000100', hint: 'The timestamp of the first message in the thread: right-click it, then Copy link; it is the number after "p".' },
    { key: 'text', label: 'Message' },
  ],
  gsheets_read: [
    { key: 'spreadsheet_id', label: 'Spreadsheet ID', placeholder: '1AbC...xYz', hint: 'In the sheet URL, the long text between /d/ and /edit.' },
    { key: 'range', label: 'Range', optional: true, placeholder: 'Sheet1!A1:D20' },
  ],
  gsheets_update: [
    { key: 'spreadsheet_id', label: 'Spreadsheet ID', placeholder: '1AbC...xYz', hint: 'In the sheet URL, the long text between /d/ and /edit.' },
    { key: 'range', label: 'Range', placeholder: 'Sheet1!A1:D20' },
    { key: 'data', label: 'Data' },
  ],
  gsheets_create: [{ key: 'title', label: 'Title' }],
  gdrive_list_files: [{ key: 'limit', label: 'Limit', optional: true }, { key: 'query', label: 'Query', optional: true }],
  gdrive_search_files: [{ key: 'query', label: 'Search for' }],
  gdrive_get_file: [
    { key: 'file_id', label: 'File ID', placeholder: '1AbC...xYz', hint: 'In Drive, open the file and copy the text after /d/ (or after id=) in its URL.' },
  ],
};

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const DEFAULT_MODEL = '__provider_default__';

function BranchRows({ nodeId, cfgType, cfg }: { nodeId: string; cfgType: string; cfg: Cfg }) {
  const { activeFlow, setSelectedNode } = useFlowContext();
  const handles = branchHandlesFor(cfgType, cfg);
  if (handles.length === 0) return null;
  return (
    <div className="space-y-1.5" data-testid="flow-branches">
      <Label size="sm">Where each path goes</Label>
      <p className="text-[11px] text-muted-foreground">Drag from the matching dot on the step, or use its Add step button.</p>
      {handles.map((h) => {
        const edge = activeFlow?.edges.find((e) => e.source === nodeId && edgeRoute(e) === h.route);
        const target = activeFlow?.nodes.find((n) => n.id === edge?.target);
        return (
          <div key={h.route} className="flex items-center justify-between rounded-md border border-border px-2 py-1.5 text-xs" data-testid={`flow-branch-${h.route}`}>
            <span className="font-medium">{h.label}</span>
            {target ? (
              <button type="button" className="text-primary hover:underline truncate max-w-[150px]" onClick={() => setSelectedNode(target.id)}>
                {target.data.label}
              </button>
            ) : (
              <span className="text-muted-foreground" data-testid={`flow-branch-${h.route}-empty`}>Not connected</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function ActionConfigForm({ nodeId }: { nodeId: string }) {
  const { node, cfg, patch, kind, shell, activeFlow } = useNodeForm(nodeId, 'actionConfig');
  const { updateEdges } = useFlowContext();
  const type = str(cfg.type);
  const [agents, setAgents] = useState<Opt[]>([]);
  const [roles, setRoles] = useState<Array<Opt & { subtitle?: string }>>([]);
  const [tools, setTools] = useState<Array<Opt & { subtitle?: string }>>([]);
  const [toolsByName, setToolsByName] = useState<Record<string, FlowTool>>({});
  const [loading, setLoading] = useState(false);
  const [modelGroups, setModelGroups] = useState<Array<{ provider: string; models: Opt[] }>>([]);

  useEffect(() => {
    if (type !== 'router') return;
    Promise.all([getModels(), getProviders()])
      .then(([models, providers]) => {
        const names = new Map((providers as Array<{ name: string; provider_name?: string }>).map((p) => [p.name, p.provider_name || p.name]));
        const groups = new Map<string, Opt[]>();
        for (const m of models.filter(isChatModel)) {
          const g = names.get(m.provider) ?? m.provider;
          groups.set(g, [...(groups.get(g) ?? []), { value: m.name, label: m.model_name || m.name }]);
        }
        setModelGroups([...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([provider, list]) => ({ provider, models: list })));
      })
      .catch(() => setModelGroups([]));
  }, [type]);

  useEffect(() => {
    if (type !== 'agent-run') return;
    setLoading(true);
    getAgents()
      .then((r) => {
        const items = Array.isArray(r) ? r : r.items;
        setAgents((items || []).map((a: { name: string; agent_name?: string }) => ({ value: a.name, label: a.agent_name || a.name })));
      })
      .catch(() => setAgents([]))
      .finally(() => setLoading(false));
  }, [type]);

  useEffect(() => {
    if (type !== 'human.approval') return;
    getApproverRoles()
      .then((l) => setRoles((l || []).map((r) => ({ value: r.name, label: r.name, subtitle: r.name === 'System Manager' ? 'Administrator-level role' : r.group === 'Huf' ? 'Huf role' : undefined }))))
      .catch(() => setRoles([]));
  }, [type]);

  useEffect(() => {
    if (type !== 'tool-call') return;
    setLoading(true);
    getFlowTools()
      .then((list) => {
        registerToolSchemas(list || []);
        const by: Record<string, FlowTool> = {};
        (list || []).forEach((t) => { by[t.name] = t; });
        setToolsByName(by);
        setTools(
          (list || [])
            .filter((t) => t.name !== 'run_python')
            .map((t) => ({ value: t.name, label: toolLabel(t.name, t.label), subtitle: t.source === 'mcp' ? `MCP: ${t.mcp_server || 'server'}` : 'Built-in' }))
        );
      })
      .catch(() => { setTools([]); setToolsByName({}); })
      .finally(() => setLoading(false));
  }, [type]);

  if (!node) return null;
  const { Err } = shell;
  const title = actionLabel(actionCardId(cfg as { type?: unknown; tool_id?: unknown }));
  const f = (field: string) => tid(kind, field);
  const input = asObj(cfg.input);
  const setInput = (key: string, value: unknown) => patch({ input: { ...input, [key]: value } });

  const agentPromptPicker = (current: string, bindings: Cfg) => (
    <VariablePicker
      currentNodeId={nodeId}
      testId="flow-agent-run-variable-picker"
      onSelect={(ref, suggested) => {
        const existing = Object.entries(bindings).find(([, v]) => asObj(v).$from === ref)?.[0];
        const name = existing ?? uniqueName(suggested, Object.keys(bindings));
        patch({
          prompt: `${current}${current && !current.endsWith(' ') ? ' ' : ''}{${name}}`,
          prompt_bindings: { ...bindings, [name]: { $from: ref } },
        });
      }}
    />
  );

  if (type === 'agent-run') {
    const prompt = str(cfg.prompt);
    const bindings = asObj(cfg.prompt_bindings);
    return (
      <Section title={title}>
        <div>
          <Label htmlFor="agent-name" size="sm">Agent</Label>
          <Combobox
            id="agent-name"
            testId={f('agent')}
            options={agents}
            value={str(cfg.agent)}
            onValueChange={(v) => patch({ agent: v })}
            placeholder={loading ? 'Loading...' : 'Choose an agent...'}
            disabled={loading}
            searchPlaceholder="Search agents..."
            emptyText={agents.length ? 'No matching agent.' : 'No agents are available to your account.'}
            linkTo={linkRoutes.agent}
          />
          <Err field="agent" />
        </div>
        <div>
          <div className="flex justify-between items-center mb-1">
            <Label htmlFor="agent-prompt" size="sm">Prompt</Label>
            {agentPromptPicker(prompt, bindings)}
          </div>
          <Textarea
            id="agent-prompt"
            data-testid={f('prompt')}
            className="min-h-[80px] w-full"
            value={prompt}
            onChange={(e) => patch({ prompt: e.target.value })}
            placeholder="What should the agent do? Use {name} to include data from an earlier step."
          />
          <Err field="prompt" />
        </div>
        {Object.keys(bindings).length > 0 && (
          <div className="space-y-2" data-testid={f('prompt_bindings')}>
            <Label size="sm">Data used in the prompt</Label>
            {Object.entries(bindings).map(([name, value]) => (
              <div key={name} className="flex items-center gap-2" data-testid={`flow-binding-${name}`}>
                <span className="font-mono text-xs w-24 shrink-0 truncate">{`{${name}}`}</span>
                <Input
                  className="font-mono text-xs"
                  aria-label={`Source for ${name}`}
                  data-testid={`flow-binding-source-${name}`}
                  value={str(asObj(value).$from)}
                  onChange={(e) => patch({ prompt_bindings: { ...bindings, [name]: { $from: e.target.value } } })}
                />
                <VariablePicker
                  currentNodeId={nodeId}
                  testId={`flow-binding-picker-${name}`}
                  label={`Pick the data for ${name}`}
                  onSelect={(ref) => patch({ prompt_bindings: { ...bindings, [name]: { $from: ref } } })}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${name}`}
                  onClick={() => {
                    const next = { ...bindings };
                    delete next[name];
                    patch({ prompt_bindings: Object.keys(next).length ? next : undefined });
                  }}
                >
                  ×
                </Button>
              </div>
            ))}
          </div>
        )}
      </Section>
    );
  }

  if (type === 'tool-call') {
    const toolId = str(cfg.tool_id);
    const isHttp = toolId === 'http_request';
    const schemaProps = asObj(asObj(toolsByName[toolId]?.params_json_schema).properties);
    const required = new Set(TOOL_REQUIRED_INPUT[toolId]?.map(([k]) => k) ?? (asObj(toolsByName[toolId]?.params_json_schema).required as string[] | undefined) ?? []);
    const cardToolIds = ACTION_CARD_CONTRACT[actionCardId(cfg as { type?: unknown; tool_id?: unknown })]?.toolIds;
    const toolOptions = cardToolIds ? tools.filter((t) => cardToolIds.includes(t.value)) : tools;
    const timeoutSec = typeof cfg.timeout_ms === 'number' ? Math.round(cfg.timeout_ms / 1000) : '';
    const presetFields = PRESET_FIELDS[toolId];
    const fields: Array<{ key: string; label: string; optional: boolean; placeholder?: string; hint?: string }> = presetFields
      ? presetFields.map((p) => ({ key: p.key, label: p.label, optional: Boolean(p.optional), placeholder: p.placeholder, hint: p.hint }))
      : Object.keys(schemaProps).map((k) => ({ key: k, label: k, optional: !required.has(k) }));

    return (
      <Section title={title}>
        {!isHttp && (
          <div>
            <Label htmlFor="tool-id" size="sm">Tool</Label>
            <Combobox
              id="tool-id"
              testId={f('tool_id')}
              options={toolOptions}
              value={toolId}
              onValueChange={(v) => { if (v && v !== toolId) patch({ tool_id: v, input: {} }); }}
              placeholder={loading ? 'Loading...' : 'Choose a tool...'}
              disabled={loading}
              searchPlaceholder="Search tools..."
              emptyText={toolOptions.length ? 'No matching tool.' : 'No tools are available to your account.'}
            />
            <Err field="tool_id" />
          </div>
        )}
        <NotConnected toolId={toolId} testIdSuffix="sidebar" />
        {isHttp ? (
          <>
            <FlowValueInput id="http-url" nodeId={nodeId} testId={f('input.url')} label="URL" placeholder="https://api.example.com/items" value={input.url} onChange={(v) => setInput('url', v)} />
            <Err field="input.url" />
            <div>
              <Label htmlFor="http-method" size="sm">Method</Label>
              <Select value={str(input.method) || 'GET'} onValueChange={(v) => setInput('method', v)}>
                <SelectTrigger id="http-method" data-testid={f('input.method')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HTTP_METHODS.map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <FlowValueInput id="http-headers" nodeId={nodeId} testId={f('input.headers')} label="Headers" optional value={input.headers} onChange={(v) => setInput('headers', v)} />
            <FlowValueInput id="http-body" nodeId={nodeId} testId={f('input.body')} label="Body" optional value={input.body} onChange={(v) => setInput('body', v)} />
          </>
        ) : toolId && fields.length > 0 ? (
          fields.map((fld) => (
            <div key={`${toolId}-${fld.key}`}>
              <FlowValueInput
                id={`tool-in-${fld.key}`}
                nodeId={nodeId}
                testId={f(`input.${fld.key}`)}
                label={fld.label}
                optional={fld.optional}
                placeholder={fld.placeholder}
                hint={fld.hint}
                value={input[fld.key]}
                onChange={(v) => setInput(fld.key, v)}
              />
              <Err field={`input.${fld.key}`} />
              {fld.key === 'channel' && toolId.startsWith('slack_send') && (
                <div className="mt-2">
                  <SlackChannelPicker value={str(input.channel)} onPick={(id) => setInput('channel', id)} />
                </div>
              )}
            </div>
          ))
        ) : toolId ? (
          <p className="text-xs text-muted-foreground">This tool needs no settings.</p>
        ) : null}
        {toolId ? (
          <div>
            <Label htmlFor="tool-timeout" size="sm">Wait up to (seconds, optional)</Label>
            <Input
              id="tool-timeout"
              data-testid={f('timeout_ms')}
              type="number"
              min={1}
              value={timeoutSec}
              onChange={(e) => patch({ timeout_ms: e.target.value === '' ? undefined : Math.max(1, parseInt(e.target.value, 10)) * 1000 })}
              placeholder="No limit"
            />
            <p className="mt-1 text-xs text-muted-foreground" data-testid={f('timeout_ms-help')}>Applies to connected (MCP) tools; built-in tools finish on their own.</p>
            <Err field="timeout_ms" />
          </div>
        ) : null}
      </Section>
    );
  }

  if (type === 'router') {
    const out = (activeFlow?.edges ?? []).filter((e) => e.source === nodeId && edgeRoute(e) === 'option');
    const labelOf = (id: string) => activeFlow?.nodes.find((n) => n.id === id)?.data.label ?? id;
    return (
      <Section title={title} hint="Connect one arrow from this step to each possible next step and name it. The AI picks the arrow whose name fits best.">
        <div>
          <PickerTextarea
            id="router-prompt"
            testId={f('prompt')}
            pickerTestId={`${f('prompt')}-picker`}
            nodeId={nodeId}
            label="How should the AI choose?"
            value={str(cfg.prompt)}
            onChange={(v) => patch({ prompt: v })}
            format={(ref) => `{${ref}}`}
            placeholder="For example: Is this request urgent or routine?"
          />
          <Err field="prompt" />
        </div>
        <div>
          <Label htmlFor="router-model" size="sm">AI model (optional)</Label>
          <Select value={str(cfg.model) || DEFAULT_MODEL} onValueChange={(v) => patch({ model: v === DEFAULT_MODEL ? undefined : v })}>
            <SelectTrigger id="router-model" data-testid={f('model')}>
              <SelectValue placeholder="Use provider default" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DEFAULT_MODEL} data-testid="flow-option-router-model-default">Use provider default</SelectItem>
              {modelGroups.map((g) => (
                <SelectGroup key={g.provider}>
                  <SelectLabel>{g.provider}</SelectLabel>
                  {g.models.map((m) => (
                    <SelectItem key={m.value} value={m.value} data-testid={`flow-option-router-model-${m.value}`}>{m.label}</SelectItem>
                  ))}
                </SelectGroup>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2" data-testid={f('options')}>
          <Label size="sm">Paths</Label>
          {out.length === 0 ? <p className="text-xs text-muted-foreground" data-testid="flow-router-no-paths">No paths yet.</p> : null}
          {out.map((e) => (
            <div key={e.id} className="flex items-center gap-2" data-testid={`flow-router-path-${e.target}`}>
              <Input
                className="min-w-0"
                title={typeof e.label === 'string' ? e.label : undefined}
                aria-label={`Label for path to ${labelOf(e.target)}`}
                data-testid={`flow-router-path-label-${e.target}`}
                value={typeof e.label === 'string' ? e.label : ''}
                placeholder="Name this path"
                onChange={(ev) => updateEdges((activeFlow?.edges ?? []).map((x) => (x.id === e.id ? { ...x, label: ev.target.value } : x)))}
              />
              <span className="text-xs text-muted-foreground truncate w-[84px] shrink-0" title={`Goes to ${labelOf(e.target)}`}>
                {'\u2192 '}{labelOf(e.target)}
              </span>
            </div>
          ))}
          <Err field="options" />
        </div>
        {out.length > 0 && (
          <div>
            <Label htmlFor="router-default" size="sm">If nothing matches, go to</Label>
            <Select value={str(cfg.default)} onValueChange={(v) => patch({ default: v })}>
              <SelectTrigger id="router-default" data-testid={f('default')}>
                <SelectValue placeholder="Choose a path..." />
              </SelectTrigger>
              <SelectContent>
                {out.map((e) => (
                  <SelectItem key={e.id} value={e.target}>{labelOf(e.target)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Err field="default" />
          </div>
        )}
      </Section>
    );
  }

  if (type === 'condition') {
    return (
      <Section title={title} hint="Checks a condition. The True path runs when it holds, otherwise the False path.">
        <div>
          <PickerTextarea
            id="condition-expr"
            testId={f('expression')}
            pickerTestId={`${f('expression')}-picker`}
            nodeId={nodeId}
            label="Condition"
            value={str(cfg.expression)}
            onChange={(v) => patch({ expression: v })}
            format={(ref) => ref.replace(/\.(\w+)/g, "['$1']")}
            className="min-h-[60px]"
            mono
            placeholder="input['amount'] > 100"
          />
          <p className="mt-1 text-[11px] text-muted-foreground">Use Insert data to add the trigger or an earlier step, then pick a field, for example input['amount'].</p>
          <Err field="expression" />
        </div>
        <BranchRows nodeId={nodeId} cfgType="condition" cfg={cfg} />
        <Err field="branch.true" />
        <Err field="branch.false" />
      </Section>
    );
  }

  if (type === 'foreach') {
    const itemsRef = str(asObj(cfg.items).$from);
    const collectRef = str(asObj(cfg.collect).$from);
    return (
      <Section title={title} hint="Runs the steps on the 'For each item' path once per item, then continues on 'When done'.">
        <div>
          <div className="flex justify-between items-center mb-1">
            <Label htmlFor="loop-items" size="sm">List to loop over</Label>
            <VariablePicker currentNodeId={nodeId} testId="flow-loop-items-picker" onSelect={(ref) => patch({ items: { $from: ref } })} />
          </div>
          <Input id="loop-items" data-testid={f('items')} className="font-mono text-xs" value={itemsRef} onChange={(e) => patch({ items: { $from: e.target.value } })} placeholder="input.recipients" />
          <Err field="items" />
        </div>
        <div>
          <Label htmlFor="loop-max" size="sm">Maximum items to process</Label>
          <Input
            id="loop-max"
            data-testid={f('max_iterations')}
            type="number"
            min={0}
            value={typeof cfg.max_iterations === 'number' ? cfg.max_iterations : ''}
            onChange={(e) => patch({ max_iterations: e.target.value === '' ? undefined : parseInt(e.target.value, 10) })}
          />
          <Err field="max_iterations" />
        </div>
        <div>
          <Label htmlFor="loop-on-error" size="sm">If one item fails</Label>
          <Select value={str(cfg.on_item_error)} onValueChange={(v) => patch({ on_item_error: v })}>
            <SelectTrigger id="loop-on-error" data-testid={f('on_item_error')}>
              <SelectValue placeholder="Choose..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fail" data-testid="flow-option-loop-on-error-fail">Stop the flow</SelectItem>
              <SelectItem value="skip" data-testid="flow-option-loop-on-error-skip">Skip that item</SelectItem>
            </SelectContent>
          </Select>
          <Err field="on_item_error" />
        </div>
        <div>
          <div className="flex justify-between items-center mb-1">
            <Label htmlFor="loop-collect" size="sm">Result to collect from each item</Label>
            <VariablePicker currentNodeId={nodeId} scope="loop-body" testId="flow-loop-collect-picker" onSelect={(ref) => patch({ collect: { $from: ref } })} />
          </div>
          <Input id="loop-collect" data-testid={f('collect')} className="font-mono text-xs" value={collectRef} onChange={(e) => patch({ collect: { $from: e.target.value } })} placeholder="n_email" />
          <Err field="collect" />
        </div>
        <BranchRows nodeId={nodeId} cfgType="foreach" cfg={cfg} />
        <Err field="branch.body" />
      </Section>
    );
  }

  if (type === 'human.approval') {
    const approverType = str(cfg.approver_type);
    const users = Array.isArray(cfg.approver_users) ? (cfg.approver_users as string[]) : [];
    const timeoutMin = typeof cfg.timeout_ms === 'number' ? Math.round(cfg.timeout_ms / 60000) : '';
    return (
      <Section title={title} hint="Pauses the flow until someone approves or rejects. Each outcome is its own path.">
        <div>
          <PickerTextarea
            id="approval-message"
            testId={f('message')}
            pickerTestId={`${f('message')}-picker`}
            nodeId={nodeId}
            label="Message for the approver"
            value={str(cfg.message)}
            onChange={(v) => patch({ message: v })}
            format={(ref) => `{${ref}}`}
            className="min-h-[60px]"
            placeholder="Approve this refund?"
          />
          <Err field="message" />
        </div>
        <div>
          <Label htmlFor="approver-type" size="sm">Who can approve</Label>
          <Select
            value={approverType}
            onValueChange={(v) =>
              patch(
                v === 'role' ? { approver_type: 'role', approver_users: undefined }
                  : v === 'user' ? { approver_type: 'user', approver_role: undefined }
                    : { approver_type: undefined, approver_role: undefined, approver_users: undefined }
              )
            }
          >
            <SelectTrigger id="approver-type" data-testid={f('approver_type')}>
              <SelectValue placeholder="Choose who can approve" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="role" data-testid="flow-option-approver-role">People with a role</SelectItem>
              <SelectItem value="user" data-testid="flow-option-approver-user">Specific people</SelectItem>
            </SelectContent>
          </Select>
          <Err field="approver_type" />
        </div>
        {approverType === 'role' && (
          <div>
            <Label htmlFor="approver-role" size="sm">Role</Label>
            <Combobox id="approver-role" testId={f('approver_role')} options={roles} value={str(cfg.approver_role)} onValueChange={(v) => patch({ approver_role: v })} placeholder="Choose a role..." searchPlaceholder="Search roles..." emptyText={roles.length ? 'No matching role.' : 'No roles are available to choose from.'} />
            <Err field="approver_role" />
          </div>
        )}
        {approverType === 'user' && (
          <div>
            <Label htmlFor="approver-users" size="sm">People (emails, comma-separated)</Label>
            <Input
              id="approver-users"
              data-testid={f('approver_users')}
              defaultValue={users.join(', ')}
              onChange={(e) => {
                const list = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
                patch({ approver_users: list.length ? list : undefined });
              }}
              placeholder="manager@company.com, cfo@company.com"
            />
            <Err field="approver_users" />
          </div>
        )}
        <div>
          <Label htmlFor="approval-timeout" size="sm">Give up after (minutes, optional)</Label>
          <Input
            id="approval-timeout"
            data-testid={f('timeout_ms')}
            type="number"
            min={1}
            value={timeoutMin}
            onChange={(e) => patch({ timeout_ms: e.target.value === '' ? undefined : Math.max(1, parseInt(e.target.value, 10)) * 60000 })}
          />
          <Err field="timeout_ms" />
        </div>
        <BranchRows nodeId={nodeId} cfgType="human.approval" cfg={cfg} />
        <Err field="branch.approve" />
        <Err field="branch.reject" />
      </Section>
    );
  }

  if (type === 'transform') {
    const spec = getTransformOp(str(cfg.op));
    return (
      <Section title={title}>
        <div>
          <Label htmlFor="transform-op" size="sm">What to do</Label>
          <Select value={str(cfg.op)} onValueChange={(v) => patch({ op: v, input: {} })}>
            <SelectTrigger id="transform-op" data-testid={f('op')}>
              <SelectValue placeholder="Choose an operation..." />
            </SelectTrigger>
            <SelectContent>
              {TRANSFORM_OPS.map((o) => (
                <SelectItem key={o.name} value={o.name} data-testid={`flow-option-transform-op-${o.name}`}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Err field="op" />
        </div>
        {spec?.params.map((param) => (
          <div key={`${spec.name}-${param}`}>
            <FlowValueInput id={`transform-in-${param}`} nodeId={nodeId} testId={f(`input.${param}`)} label={param} optional={spec.optional?.includes(param)} value={input[param]} onChange={(v) => setInput(param, v)} />
            <Err field={`input.${param}`} />
          </div>
        ))}
      </Section>
    );
  }

  if (type === 'state-get' || type === 'state-set' || type === 'state-delete') {
    return (
      <Section title={title} hint="Saved values belong to this flow. Use a template to key by sender, for example cart:{sender}.">
        <div>
          <FlowValueInput id="state-key" nodeId={nodeId} testId={f('key')} label="Key" value={cfg.key} onChange={(v) => patch({ key: v })} />
          <Err field="key" />
        </div>
        {type === 'state-get' && <FlowValueInput id="state-default" nodeId={nodeId} testId={f('default')} label="Default" optional value={cfg.default} onChange={(v) => patch({ default: v })} />}
        {type === 'state-set' && (
          <>
            <div>
              <FlowValueInput id="state-value" nodeId={nodeId} testId={f('value')} label="Value" value={cfg.value} onChange={(v) => patch({ value: v })} />
              <Err field="value" />
            </div>
            <div>
              <Label htmlFor="state-ttl" size="sm">Keep for (seconds, optional, max 2592000)</Label>
              <Input
                id="state-ttl"
                data-testid={f('ttl_seconds')}
                type="number"
                min={1}
                max={2592000}
                value={typeof cfg.ttl_seconds === 'number' ? cfg.ttl_seconds : ''}
                onChange={(e) => patch({ ttl_seconds: e.target.value === '' ? undefined : parseInt(e.target.value, 10) })}
              />
            </div>
          </>
        )}
      </Section>
    );
  }

  if (type === 'doc-create') {
    const fields = asObj(cfg.fields);
    const entries = Object.entries(fields);
    return (
      <Section title={title} hint="Only document types your administrator has allowed can be created here.">
        <div>
          <Label htmlFor="doc-create-doctype" size="sm">Document type</Label>
          <Input id="doc-create-doctype" data-testid={f('doctype')} value={str(cfg.doctype)} onChange={(e) => patch({ doctype: e.target.value })} placeholder="ToDo" />
          <Err field="doctype" />
        </div>
        {entries.map(([name, val], i) => (
          <div key={i} className="p-3 bg-muted/20 border rounded-md space-y-2">
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Label htmlFor={`doc-field-${i}-name`} size="sm">Field name</Label>
                <Input id={`doc-field-${i}-name`} data-testid={f(`fields.${i}.name`)} value={name} onChange={(e) => patch({ fields: Object.fromEntries(entries.map(([k, v], j) => (j === i ? [e.target.value, v] : [k, v]))) })} />
              </div>
              <Button variant="ghost" size="sm" aria-label="Remove field" className="h-8 px-2 text-destructive" onClick={() => patch({ fields: Object.fromEntries(entries.filter((_, j) => j !== i)) })}>×</Button>
            </div>
            <FlowValueInput id={`doc-field-${i}-value`} nodeId={nodeId} testId={f(`fields.${i}.value`)} label="Value" value={val} onChange={(v) => patch({ fields: Object.fromEntries(entries.map(([k, o], j) => (j === i ? [k, v] : [k, o]))) })} />
          </div>
        ))}
        <Button variant="outline" size="sm" className="w-full" data-testid={f('fields.add')} onClick={() => patch({ fields: { ...fields, [`field_${entries.length + 1}`]: '' } })}>
          Add field
        </Button>
      </Section>
    );
  }

  if (type === 'unknown') {
    return (
      <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md">
        This step type cannot be edited here. It is kept as it is and saved unchanged.
      </div>
    );
  }
  return null;
}
