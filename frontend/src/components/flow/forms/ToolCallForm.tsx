import { useEffect, useState } from 'react';
import { ACTION_CARD_CONTRACT } from '../../../data/actions';
import { Combobox } from '../../ui/combobox';
import { FieldHint } from '../FieldHint';
import { FlowValueInput } from '../../FlowValueInput';
import { INTEGRATION_NEEDS } from '@/lib/flow/flowHelp';
import { Label } from '../../ui/label';
import { MoreOptions } from '../frame/MoreOptions';
import { PRESET_FIELDS } from './toolPresetFields';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { SlackChannelPicker } from '../SlackChannelPicker';
import { TOOL_REQUIRED_INPUT } from '@/lib/flow-graph/flowValidation';
import { actionCardId } from '@/lib/flow/flowLabels';
import { registerToolSchemas } from '@/lib/flow/flowToolSchemas';
import { toolLabel } from '@/lib/flow/flowIntegrations';
import { type ActionFormProps, asObj, type Opt, Section, str } from './formKit';
import { type FlowTool, getFlowTools } from '../../../services/toolApi';

const isEmptyValue = (v: unknown) => v === undefined || v === null || v === '' || (typeof v === 'object' && v !== null && Object.keys(v).length === 0);

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

/** Fields that hold a list or a set of named values (JSON area) and fields that hold a message (taller box). */
const JSON_FIELDS = new Set(['data']);
const LONG_FIELDS = new Set(['body', 'text', 'message', 'content']);

export function ToolCallForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const input = asObj(cfg.input);
  const setInput = (key: string, value: unknown) => patch({ input: { ...input, [key]: value } });
  const [tools, setTools] = useState<Array<Opt & { subtitle?: string }>>([]);
  const [toolsByName, setToolsByName] = useState<Record<string, FlowTool>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
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
  }, []);
  const toolId = str(cfg.tool_id);
  const isHttp = toolId === 'http_request';
  const schemaProps = asObj(asObj(toolsByName[toolId]?.params_json_schema).properties);
  const required = new Set(TOOL_REQUIRED_INPUT[toolId]?.map(([k]) => k) ?? (asObj(toolsByName[toolId]?.params_json_schema).required as string[] | undefined) ?? []);
  const cardToolIds = ACTION_CARD_CONTRACT[actionCardId(cfg as { type?: unknown; tool_id?: unknown })]?.toolIds;
  const toolOptions = cardToolIds ? tools.filter((t) => cardToolIds.includes(t.value)) : tools;
  const presetFields = PRESET_FIELDS[toolId];
  const fields: Array<{ key: string; label: string; optional: boolean; placeholder?: string; hint?: string }> = presetFields
    ? presetFields.map((p) => ({ key: p.key, label: p.label, optional: Boolean(p.optional), placeholder: p.placeholder, hint: p.hint }))
    : Object.keys(schemaProps).map((k) => {
      const d = asObj(schemaProps[k]).description;
      return { key: k, label: k, optional: !required.has(k), hint: typeof d === 'string' ? d : undefined };
    });
  const cardId = actionCardId(cfg as { type?: unknown; tool_id?: unknown });
  const toolHint = isHttp
    ? 'Calls a web address and hands the response to the next step. Addresses on private networks are blocked.'
    : `Runs one tool and hands its result to the next step.${INTEGRATION_NEEDS[cardId] ? ` ${INTEGRATION_NEEDS[cardId]}` : ''}`;

  const renderField = (fld: (typeof fields)[number]) => (
    <div key={`${toolId}-${fld.key}`}>
      <FlowValueInput
        id={`tool-in-${fld.key}`}
        nodeId={nodeId}
        testId={f(`input.${fld.key}`)}
        label={fld.label}
        optional={fld.optional}
        placeholder={fld.placeholder}
        hint={fld.hint}
        kind={JSON_FIELDS.has(fld.key) ? 'json' : LONG_FIELDS.has(fld.key) ? 'longtext' : undefined}
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
  );

  return (
    <Section title={title} hint={toolHint}>
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
          <FieldHint testId="flow-hint-tool-id">Choose what this step should do. Its settings appear below.</FieldHint>
          <Err field="tool_id" />
        </div>
      )}
      {isHttp ? (
        <>
          <FlowValueInput id="http-url" nodeId={nodeId} testId={f('input.url')} label="URL" placeholder="https://api.example.com/items" hint="The full address, starting with https://. Click + Use data to add a value from an earlier step." value={input.url} onChange={(v) => setInput('url', v)} />
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
            <FieldHint testId="flow-hint-http-method">GET reads data. POST, PUT and PATCH send the Body. DELETE removes something.</FieldHint>
          </div>
          <MoreOptions defaultOpen={Boolean(input.headers || input.body)}>
          <FlowValueInput id="http-headers" nodeId={nodeId} testId={f('input.headers')} label="Headers" optional kind="json" hint={'Extra request headers, for example {"Authorization": "Bearer your-key"}.'} value={input.headers} onChange={(v) => setInput('headers', v)} />
          <FlowValueInput id="http-body" nodeId={nodeId} testId={f('input.body')} label="Body" optional kind="json" hint={'The data to send with POST, PUT or PATCH, for example {"name": "Ada"}.'} value={input.body} onChange={(v) => setInput('body', v)} />
          </MoreOptions>
        </>
      ) : toolId && fields.length > 0 ? (
        <>
          {fields.filter((fld) => !fld.optional).map(renderField)}
          {fields.some((fld) => fld.optional) && (
            <MoreOptions defaultOpen={fields.some((fld) => fld.optional && !isEmptyValue(input[fld.key]))}>
              {fields.filter((fld) => fld.optional).map(renderField)}
            </MoreOptions>
          )}
        </>
      ) : toolId ? (
        <p className="text-xs text-muted-foreground" data-testid="flow-hint-tool-no-settings">This tool needs no settings. It runs as soon as the step before it finishes.</p>
      ) : null}
    </Section>
  );
}
