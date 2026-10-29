import type { ActionConfig, FlowNodeData, TriggerConfig } from '../../types/flow.types';
import { describeCron } from '../flow-graph/flowSchedule';
import { getTransformOp } from '../flow-graph/flowTransformOps';
import { toolLabel } from './flowIntegrations';

/**
 * What a canvas card says besides its title: one plain-words subtitle (what the step does) and ONE status word.
 * Pure functions so every card kind reads the same way and the wording is unit tested.
 */

/** The single status vocabulary on cards. `kind` drives colour, `text` is the word shown. */
export type CardStatusKind = 'ready' | 'needs-setup' | 'not-connected' | 'orphan' | 'running' | 'waiting' | 'done' | 'failed';

export interface CardStatus {
  kind: CardStatusKind;
  text: string;
}

export const CARD_STATUS_TEXT: Record<CardStatusKind, string> = {
  ready: 'Ready',
  'needs-setup': 'Needs setup',
  'not-connected': 'Not connected',
  orphan: 'Nothing leads here',
  running: 'Running',
  waiting: 'Waiting',
  done: 'Done',
  failed: 'Failed',
};

interface StatusInput {
  runStatus: FlowNodeData['status'];
  incomplete: boolean;
  orphaned: boolean;
  notConnected: boolean;
}

/** Highest priority first: what the last run did, then what is missing, then "Ready". */
export function cardStatus({ runStatus, incomplete, orphaned, notConnected }: StatusInput): CardStatus {
  const kind: CardStatusKind =
    runStatus === 'running' ? 'running'
      : runStatus === 'waiting' ? 'waiting'
        : runStatus === 'error' ? 'failed'
          : runStatus === 'success' ? 'done'
            : notConnected ? 'not-connected'
              : incomplete ? 'needs-setup'
                : orphaned ? 'orphan'
                  : 'ready';
  return { kind, text: CARD_STATUS_TEXT[kind] };
}

/** A plain text value the user typed; references, templates and empty values give undefined. */
function typed(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v.trim() : undefined;
}

function hostOf(url: unknown): string | undefined {
  const u = typed(url);
  if (!u) return undefined;
  try {
    return new URL(u).host || undefined;
  } catch {
    return undefined;
  }
}

const DOC_EVENT_WORD: Record<string, string> = {
  after_insert: 'created',
  on_update: 'changed',
  on_submit: 'submitted',
  on_cancel: 'cancelled',
  on_trash: 'deleted',
};

export function triggerSubtitle(cfg: TriggerConfig | undefined): string {
  switch (cfg?.type) {
    case 'webhook':
      return 'Runs on a web request';
    case 'schedule': {
      const text = describeCron(cfg.cron).replace(/ \(server time\)$/, '');
      return text.startsWith('No valid') ? 'Pick when it should run' : text;
    }
    case 'doc-event': {
      const dt = typed(cfg.doctype);
      const ev = cfg.event ? DOC_EVENT_WORD[cfg.event] : undefined;
      if (dt && ev) return `When a ${dt} is ${ev}`;
      return dt ? `When a ${dt} changes` : 'Starts when a record changes';
    }
    default:
      return 'Choose what starts this flow';
  }
}

export function toolSubtitle(cfg: Extract<ActionConfig, { type: 'tool-call' }>): string {
  const id = typed(cfg.tool_id);
  const input = (cfg.input ?? {}) as Record<string, unknown>;
  switch (id) {
    case undefined:
      return 'Pick what it should do';
    case 'slack_send_message': {
      const channel = typed(input.channel);
      return channel ? `Send a message to ${channel}` : 'Send a Slack message';
    }
    case 'slack_send_thread_reply':
      return 'Reply in a Slack thread';
    case 'gmail_send_email': {
      const to = typed(input.to);
      return to ? `Send an email to ${to}` : 'Send an email';
    }
    case 'gsheets_read':
      return 'Read a spreadsheet';
    case 'gsheets_update':
      return 'Update a spreadsheet';
    case 'gsheets_create':
      return 'Create a spreadsheet';
    case 'gdrive_list_files':
      return 'List files in Google Drive';
    case 'gdrive_search_files':
      return 'Search files in Google Drive';
    case 'gdrive_get_file':
      return 'Get a file from Google Drive';
    case 'http_request': {
      const host = hostOf(input.url);
      return host ? `Call ${host}` : 'Call a web address';
    }
    default:
      return toolLabel(id);
  }
}

/** One line saying what the step does, in the user's own values when they are plain text. */
export function actionSubtitle(cfg: ActionConfig | undefined): string {
  if (!cfg) return '';
  switch (cfg.type) {
    case 'agent-run': {
      const agent = typed(cfg.agent);
      return agent ? `Ask ${agent}` : 'Ask an AI agent to do a task';
    }
    case 'tool-call':
      return toolSubtitle(cfg);
    case 'router':
      return 'AI picks the next path';
    case 'router-decision':
      return 'Picks the next path by a rule';
    case 'condition':
      return 'Go one of two ways';
    case 'foreach':
      return 'Once for every item in a list';
    case 'human.approval': {
      const role = typed(cfg.approver_role);
      if (cfg.approver_type === 'role' && role) return `Waits for ${role}`;
      return 'Waits for a person to decide';
    }
    case 'validate':
      return 'Check the data is right';
    case 'transform': {
      const op = getTransformOp(cfg.op);
      return op ? op.label : 'Change text or data';
    }
    case 'state-get': {
      const key = typed(cfg.key);
      return key ? `Look up "${key}"` : 'Look up saved data';
    }
    case 'state-set': {
      const key = typed(cfg.key);
      return key ? `Save "${key}" for later` : 'Save data for later';
    }
    case 'state-delete': {
      const key = typed(cfg.key);
      return key ? `Forget "${key}"` : 'Forget saved data';
    }
    case 'doc-create': {
      const dt = typed(cfg.doctype);
      return dt ? `Create a ${dt}` : 'Create a record';
    }
    case 'code-run':
      return 'Run a Python snippet';
    default:
      return '';
  }
}

export const END_SUBTITLE = 'Ends the flow';
