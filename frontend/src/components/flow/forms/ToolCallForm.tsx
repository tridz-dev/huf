import { useEffect, useState } from 'react';
import { ACTION_CARD_CONTRACT } from '../../../data/actions';
import { Combobox } from '../../ui/combobox';
import { FieldHint } from '../FieldHint';
import { HttpJsonField } from './HttpFields';
import { INTEGRATION_NEEDS } from '@/lib/flow/flowHelp';
import { Label } from '../../ui/label';
import { MoreOptions } from '../frame/MoreOptions';
import { fieldFromSchema, normalizePasted, PRESET_FIELDS, type PresetField } from './toolPresetFields';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { SlackChannelField } from './SlackChannelField';
import { TOOL_REQUIRED_INPUT } from '@/lib/flow-graph/flowValidation';
import { ValueField } from './fields';
import { actionCardId } from '@/lib/flow/flowLabels';
import { integrationForTool, toolLabel } from '@/lib/flow/flowIntegrations';
import { registerToolSchemas } from '@/lib/flow/flowToolSchemas';
import { type ActionFormProps, asObj, type Opt, Section, str } from './formKit';
import { type FlowTool, getFlowTools } from '../../../services/toolApi';

const isEmptyValue = (v: unknown) => v === undefined || v === null || v === '' || (typeof v === 'object' && v !== null && Object.keys(v).length === 0);

const HTTP_METHODS: Array<{ value: string; label: string; help: string }> = [
  { value: 'GET', label: 'GET: read', help: 'Gets data from the address. Nothing is changed there.' },
  { value: 'POST', label: 'POST: create or send', help: 'Sends the request body, usually to create something new.' },
  { value: 'PUT', label: 'PUT: replace', help: 'Sends the request body to replace something that exists.' },
  { value: 'PATCH', label: 'PATCH: change part', help: 'Sends the request body to change part of something.' },
  { value: 'DELETE', label: 'DELETE: remove', help: 'Removes the thing at the address.' },
];

const SOURCE_WORDS = (t: FlowTool): string => {
  const app = integrationForTool(t.name);
  if (app) return { slack: 'Slack', gmail: 'Gmail', google_drive: 'Google Drive', google_sheets: 'Google Sheets' }[app] ?? 'App';
  return t.source === 'mcp' ? `From ${t.mcp_server || 'a connected app'}` : 'Built in';
};

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
            .map((t) => ({ value: t.name, label: toolLabel(t.name, t.label), subtitle: SOURCE_WORDS(t) }))
        );
      })
      .catch(() => { setTools([]); setToolsByName({}); })
      .finally(() => setLoading(false));
  }, []);
  const toolId = str(cfg.tool_id);
  const isHttp = toolId === 'http_request';
  const schema = asObj(toolsByName[toolId]?.params_json_schema);
  const schemaProps = asObj(schema.properties);
  const required = new Set(TOOL_REQUIRED_INPUT[toolId]?.map(([k]) => k) ?? (schema.required as string[] | undefined) ?? []);
  const cardId = actionCardId(cfg as { type?: unknown; tool_id?: unknown });
  const contract = ACTION_CARD_CONTRACT[cardId];
  const cardToolIds = contract?.toolIds ?? (contract?.toolId ? [contract.toolId] : undefined);
  const toolOptions = cardToolIds ? tools.filter((t) => cardToolIds.includes(t.value)) : tools;
  // A card that does one thing (Send email) needs no "what to do" choice; one that does several (Sheets) or the open-ended Call tool does.
  const showToolChoice = !isHttp && !(cardToolIds && cardToolIds.length === 1 && toolId === cardToolIds[0]);
  const presetFields = PRESET_FIELDS[toolId];
  const fields: PresetField[] = presetFields ?? Object.keys(schemaProps).map((k) => fieldFromSchema(k, asObj(schemaProps[k]), required.has(k)));
  const isSlack = toolId.startsWith('slack_send');
  const toolHint = isHttp
    ? 'Calls a web address and gives the answer to the next step. Addresses on private networks are blocked.'
    : `${toolSentence(toolId, cardId)}${INTEGRATION_NEEDS[cardId] ? ` ${INTEGRATION_NEEDS[cardId]}` : ''}`;

  const renderField = (fld: PresetField) => {
    if (fld.key === 'channel' && isSlack) {
      return (
        <SlackChannelField
          key={`${toolId}-channel`}
          nodeId={nodeId}
          testId={f('input.channel')}
          value={input.channel}
          onChange={(v) => setInput('channel', v)}
          Err={<Err field="input.channel" />}
          hint={fld.hint ?? ''}
        />
      );
    }
    return (
      <ValueField
        key={`${toolId}-${fld.key}`}
        field={`input.${fld.key}`}
        f={f}
        Err={Err}
        nodeId={nodeId}
        label={fld.label}
        optional={fld.optional}
        placeholder={fld.placeholder}
        hint={fld.hint}
        kind={fld.kind}
        value={input[fld.key]}
        onChange={(v) => setInput(fld.key, normalizePasted(fld.normalize, v))}
      />
    );
  };

  return (
    <Section title={title} hint={toolHint}>
      {showToolChoice && (
        <div>
          <Label htmlFor="tool-id" size="sm">{cardToolIds ? 'What to do' : 'What this step runs'}</Label>
          <Combobox
            id="tool-id"
            testId={f('tool_id')}
            options={toolOptions}
            value={toolId}
            onValueChange={(v) => { if (v && v !== toolId) patch({ tool_id: v, input: {} }); }}
            placeholder={loading ? 'Loading...' : cardToolIds ? 'Choose what to do...' : 'Search the apps and tools you can use...'}
            disabled={loading}
            searchPlaceholder="Search..."
            emptyText={toolOptions.length ? 'Nothing matches that. Try another word.' : 'Nothing is available to your account yet.'}
          />
          <FieldHint testId="flow-hint-tool-id">{cardToolIds ? 'Choose what this step should do. The settings for it appear below.' : 'Choose an app action or a built-in tool. The settings for it appear below.'}</FieldHint>
          <Err field="tool_id" />
        </div>
      )}
      {isHttp ? (
        <>
          <ValueField field="input.url" f={f} Err={Err} nodeId={nodeId} label="Web address" kind="url" placeholder="https://api.yourshop.com/orders" hint="The full address to call, starting with https://. Use + Use data to put in a value from an earlier step, like an order number." value={input.url} onChange={(v) => setInput('url', v)} />
          <div>
            <Label htmlFor="http-method" size="sm">What to do there</Label>
            <Select value={str(input.method) || 'GET'} onValueChange={(v) => setInput('method', v)}>
              <SelectTrigger id="http-method" data-testid={f('input.method')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {HTTP_METHODS.map((m) => (
                  <SelectItem key={m.value} value={m.value} description={m.help} data-testid={`flow-option-http-method-${m.value}`}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldHint testId="flow-hint-http-method">{HTTP_METHODS.find((m) => m.value === (str(input.method) || 'GET'))?.help} Most services want GET to read and POST to send.</FieldHint>
          </div>
          <MoreOptions defaultOpen={Boolean(!isEmptyValue(input.headers) || !isEmptyValue(input.body))}>
            <HttpJsonField
              surfaceKey="headers"
              title="Extra details to send (headers)"
              help={'Extra information the service asks for, most often a key to prove who you are. For example: Authorization = Bearer your-key. Switch to JSON to paste a whole set.'}
              example={{ Authorization: 'Bearer your-key' }}
              value={input.headers}
              onChange={(v) => setInput('headers', v)}
              nodeId={nodeId}
              rows={{ keyLabel: 'Name', valueLabel: 'Value', keyPlaceholder: 'Authorization', valuePlaceholder: 'Bearer your-key', addLabel: 'Add a detail' }}
            />
            <HttpJsonField
              surfaceKey="body"
              title="Request body (JSON)"
              help={'The data sent with POST, PUT or PATCH, written as JSON. Fill in the fields, or edit it as JSON if the service gives you an example to copy. Text that is not valid JSON is sent exactly as written.'}
              example={{ name: 'Ada Lovelace', email: 'ada@example.com' }}
              value={input.body}
              onChange={(v) => setInput('body', v)}
              nodeId={nodeId}
              rows={{ keyLabel: 'Field', valueLabel: 'Value', keyPlaceholder: 'name', valuePlaceholder: 'Ada Lovelace', addLabel: 'Add a field' }}
            />
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
        <p className="text-xs text-muted-foreground" data-testid="flow-hint-tool-no-settings">This step needs no settings. It runs as soon as the step before it finishes.</p>
      ) : null}
    </Section>
  );
}

/** One plain sentence for the (i) of a tool step. */
function toolSentence(toolId: string, cardId: string): string {
  if (toolId === 'gmail_send_email') return 'Sends an email from your connected Gmail account. A test run shows what would be sent, without sending it.';
  if (toolId.startsWith('slack_send')) return 'Posts a message in Slack. A test run shows what would be posted, without posting it.';
  if (toolId.startsWith('gsheets_')) return toolId === 'gsheets_read' ? 'Reads rows from a Google Sheet and gives them to the next step.' : toolId === 'gsheets_update' ? 'Writes rows into a Google Sheet.' : toolId === 'gsheets_create' ? 'Creates a new Google Sheet.' : 'Works with a Google Sheet.';
  if (toolId.startsWith('gdrive_')) return 'Looks for files in Google Drive and gives them to the next step.';
  return cardId === 'tool' ? 'Runs an action in one of your apps, or a built-in tool, and gives the result to the next step.' : 'Does one thing and gives the result to the next step.';
}
