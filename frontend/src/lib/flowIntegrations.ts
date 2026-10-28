/**
 * Integration steps (Slack, Google Sheets, Google Drive, Gmail): human tool names, which integration a
 * tool needs, and where to connect it.
 */
import { useEffect, useState } from 'react';
import { getFlowIntegrationStatus, type FlowIntegrationStatus } from '../services/flowApi';

const TOOL_LABELS: Record<string, string> = {
  gmail_send_email: 'Send an email',
  slack_send_message: 'Send a message',
  slack_send_thread_reply: 'Reply in a thread',
  gsheets_read: 'Read a spreadsheet',
  gsheets_update: 'Update a spreadsheet',
  gsheets_create: 'Create a spreadsheet',
  gdrive_list_files: 'List files',
  gdrive_search_files: 'Search files',
  gdrive_get_file: 'Get a file',
  http_request: 'HTTP request',
};

const PREFIX_SERVICE: Array<[prefix: string, service: string]> = [
  ['slack_', 'slack'],
  ['gmail_', 'gmail'],
  ['gdrive_', 'google_drive'],
  ['gsheets_', 'google_sheets'],
];

/** Integration (service key) a tool needs, or undefined for tools that need none. */
export function integrationForTool(toolId: string | undefined): string | undefined {
  if (!toolId) return undefined;
  return PREFIX_SERVICE.find(([p]) => toolId.startsWith(p))?.[1];
}

/** Plain name for a tool: known tools get a friendly name, others "Slack list channels" style. */
export function toolLabel(toolId: string | undefined, apiLabel?: string): string {
  if (!toolId) return '';
  if (TOOL_LABELS[toolId]) return TOOL_LABELS[toolId];
  const source = apiLabel && apiLabel !== toolId ? apiLabel : toolId;
  const words = source.replace(/[_.]+/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Prompt of a flow-step tool call ("Tool: <id>\nArgs: ...") with the human tool name instead of the raw id. */
export function humanizeToolPrompt(prompt: string | undefined | null): string {
  if (!prompt) return '';
  return prompt.replace(/^Tool: (\S+)/, (_m, id: string) => `Tool: ${toolLabel(id)}`);
}

const LABEL_SERVICE: Record<string, string> = {
  Slack: 'slack',
  Gmail: 'gmail',
  'Google Drive': 'google_drive',
  'Google Sheets': 'google_sheets',
};

/** The integration a failed step says is not connected ("Google Sheets is not connected: ..."), if any. */
export function notConnectedService(reason: string | null | undefined): string | undefined {
  const m = /^(.+?) is not connected[.:]/.exec(reason ?? '');
  return m ? LABEL_SERVICE[m[1]] : undefined;
}

/** Where the user connects an integration (the real credentials screen, with the service preselected). */
export function connectPath(service: string): string {
  return service === 'slack'
    ? `/gateways/new?service=${service}`
    : `/integrations/new?service=${encodeURIComponent(service)}`;
}

let cached: Record<string, FlowIntegrationStatus> | null = null;
let inflight: Promise<Record<string, FlowIntegrationStatus>> | null = null;

/** Drop the cached status (call after the user may have connected something). */
export function resetIntegrationStatus() {
  cached = null;
}

/** Connection state per integration; refreshed whenever the editor mounts. */
export function useIntegrationStatus(): Record<string, FlowIntegrationStatus> {
  const [status, setStatus] = useState<Record<string, FlowIntegrationStatus>>(cached ?? {});
  useEffect(() => {
    let live = true;
    inflight ??= getFlowIntegrationStatus().finally(() => {
      inflight = null;
    });
    inflight.then((s) => {
      cached = s;
      if (live) setStatus(s);
    });
    return () => {
      live = false;
    };
  }, []);
  return status;
}

/** True only when the status is known and says the integration this tool needs has no credentials. */
export function isToolUnconnected(toolId: string | undefined, status: Record<string, FlowIntegrationStatus>): boolean {
  const service = integrationForTool(toolId);
  return Boolean(service && status[service] && !status[service].connected);
}

/** Steps of a flow whose integration has no credentials: `[{ stepLabel, service }]`. */
export function unconnectedSteps(
  nodes: Array<{ data: { label?: string; actionConfig?: unknown } }>,
  status: Record<string, FlowIntegrationStatus>
): Array<{ stepLabel: string; service: string }> {
  const out: Array<{ stepLabel: string; service: string }> = [];
  for (const n of nodes) {
    const cfg = n.data.actionConfig as { type?: string; tool_id?: string } | undefined;
    if (cfg?.type !== 'tool-call' || !isToolUnconnected(cfg.tool_id, status)) continue;
    const service = integrationForTool(cfg.tool_id) as string;
    out.push({ stepLabel: n.data.label || toolLabel(cfg.tool_id), service: status[service].label });
  }
  return out;
}
