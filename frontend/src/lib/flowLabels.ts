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
