import { findActionOption } from '../flow-graph/appNodeTypes';
import { findTriggerOption } from '../../data/triggers';
import { triggerIsConfigured } from '../flow-gateway/gatewayDefaults';
import type { TriggerConfig } from '../../types/flow.types';

/**
 * One name per step kind: the palette card name is the node title and the sidebar title.
 * Derive it from the palette data so the three can never drift apart.
 */
export function actionLabel(actionId: string): string {
  return findActionOption(actionId)?.name ?? 'Action';
}

export function triggerLabel(triggerId: string | undefined): string {
  const option = findTriggerOption(triggerId);
  return option?.nodeTitle ?? option?.name ?? 'What starts the flow';
}

/** Palette icon name of a trigger kind (the webhook's when nothing is chosen). */
export function triggerIcon(triggerId: string | undefined): string {
  return findTriggerOption(triggerId)?.icon ?? 'Webhook';
}

/** The fields of a trigger step that follow from its config: its title, icon and whether it is set up. */
export function triggerStepFields(config: TriggerConfig) {
  return { label: triggerLabel(config.type), icon: triggerIcon(config.type), configured: triggerIsConfigured(config), triggerConfig: config };
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
export function actionCardId(config: { type?: unknown; tool_id?: unknown; backend_type?: unknown } | undefined): string {
  const type = typeof config?.type === 'string' ? config.type : '';
  // The canvas config type is `foreach`; the palette card is called `loop`.
  if (type === 'foreach') return 'loop';
  if (type === 'router-decision') return 'switch';
  // A step an app added keeps its own type id, which is also its palette id.
  if (type === 'unknown') return typeof (config as { backend_type?: unknown }).backend_type === 'string' ? (config as { backend_type: string }).backend_type : type;
  if (type === 'tool-call' && typeof config?.tool_id === 'string' && TOOL_CARD[config.tool_id]) return TOOL_CARD[config.tool_id];
  return type;
}
