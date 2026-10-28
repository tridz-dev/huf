import { actionOptions } from '../data/actions';
import { triggerOptions } from '../data/triggers';

/**
 * One name per step kind: the palette card name is the node title and the sidebar title.
 * Derive it from the palette data so the three can never drift apart.
 */
export function actionLabel(actionId: string): string {
  return actionOptions.find((a) => a.id === actionId)?.name ?? 'Action';
}

export function triggerLabel(triggerId: string | undefined): string {
  return triggerOptions.find((t) => t.id === triggerId)?.name ?? 'Trigger';
}

const TOOL_CARD: Record<string, string> = {
  gmail_send_email: 'email',
  slack_send_message: 'slack',
  slack_send_thread_reply: 'slack',
  gsheets_read: 'sheets',
  gsheets_update: 'sheets',
  gsheets_create: 'sheets',
  gdrive_list_files: 'file',
  gdrive_search_files: 'file',
  gdrive_get_file: 'file',
  http_request: 'http-request',
};

/** Palette card id (data/actions.ts) that produced an action config, so titles can be derived from it. */
export function actionCardId(config: { type?: unknown; tool_id?: unknown } | undefined): string {
  const type = typeof config?.type === 'string' ? config.type : '';
  if (type === 'tool-call' && typeof config?.tool_id === 'string' && TOOL_CARD[config.tool_id]) return TOOL_CARD[config.tool_id];
  return type;
}
