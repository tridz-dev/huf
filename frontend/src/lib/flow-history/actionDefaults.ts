import type { ActionConfig } from '../../types/flow.types';
import { getAppNodeType } from '../flow-graph/appNodeTypes';
import { CODE_RUN_ACTION, DEFAULT_CODE_PROFILE, DEFAULT_CODE_TIMEOUT_S } from '../flow-graph/codeFlow';

/** What a freshly added step of this kind starts with (the "Add step" picker and the Cmd+K palette both use it). */
export function defaultActionConfig(actionId: string, defaultCodeProfile?: string | null): ActionConfig {
  const tool = (tool_id: string, input: Record<string, unknown> = {}) => ({ type: 'tool-call', tool_id, input });
  const configs: Record<string, Record<string, unknown>> = {
    'agent-run': { type: 'agent-run', agent: '', prompt: '' },
    'tool-call': tool(''),
    condition: { type: 'condition', expression: '' },
    router: { type: 'router', prompt: '' },
    loop: { type: 'foreach', items: { $from: '' }, max_iterations: 100, on_item_error: 'fail', collect: { $from: '' } },
    'human.approval': { type: 'human.approval', message: '' },
    wait: { type: 'wait', mode: 'duration', duration: { unit: 'hours' } },
    stop: { type: 'stop', message: '' },
    'doc-get': { type: 'doc-get', doctype: '' },
    'doc-update': { type: 'doc-update', doctype: '', name: '', values: {} },
    'flow-call': { type: 'flow-call', flow_id: '', input: {}, mode: 'fire_and_forget' },
    end: { type: 'end' },
    'http-request': tool('http_request', { url: '', method: 'GET' }),
    transform: { type: 'transform', op: 'lower', input: {} },
    'state-get': { type: 'state-get', key: '' },
    'state-set': { type: 'state-set', key: '', value: '' },
    'state-delete': { type: 'state-delete', key: '' },
    'doc-create': { type: 'doc-create', doctype: '', fields: {} },
    [CODE_RUN_ACTION]: { type: 'code-run', code: '', profile: defaultCodeProfile || DEFAULT_CODE_PROFILE, inputs: {}, timeout_s: DEFAULT_CODE_TIMEOUT_S },
    email: tool('gmail_send_email'),
    slack: tool('slack_send_message'),
    sheets: tool('gsheets_read'),
    file: tool('gdrive_list_files'),
  };
  // A step an installed app added: kept as its own type, edited by the schema form.
  if (getAppNodeType(actionId)) return { type: 'unknown', backend_type: actionId } as ActionConfig;
  return (configs[actionId] ?? { type: undefined }) as unknown as ActionConfig;
}
