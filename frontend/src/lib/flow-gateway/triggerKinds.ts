import type { GatewayTriggerNodeType } from './gatewayTrigger.types';

/**
 * The one table of chat trigger kinds. Serializer, validation, icons and labels read it; nothing else lists
 * `trigger.gateway` / `trigger.whatsapp` / `trigger.telegram` by hand.
 */
export interface GatewayTriggerKind {
  /** Editor-side kind id (the `TriggerType` value WP3 adds). */
  id: 'gateway' | 'whatsapp' | 'telegram';
  nodeType: GatewayTriggerNodeType;
  /** Provider the Gateway must have, or null for any. */
  provider: string | null;
  /** Picker card title (plain words). */
  title: string;
  /** Short phrase for "When someone messages Support (...)". */
  channelWord: string;
}

export const GATEWAY_TRIGGER_KINDS: readonly GatewayTriggerKind[] = [
  { id: 'gateway', nodeType: 'trigger.gateway', provider: null, title: 'A chat message', channelWord: 'chat' },
  { id: 'whatsapp', nodeType: 'trigger.whatsapp', provider: 'WhatsApp', title: 'A WhatsApp message', channelWord: 'WhatsApp' },
  { id: 'telegram', nodeType: 'trigger.telegram', provider: 'Telegram', title: 'A Telegram message', channelWord: 'Telegram' },
];

export function gatewayKindForNodeType(nodeType: string): GatewayTriggerKind | undefined {
  return GATEWAY_TRIGGER_KINDS.find((kind) => kind.nodeType === nodeType);
}

export function isGatewayTriggerNodeType(nodeType: string): nodeType is GatewayTriggerNodeType {
  return gatewayKindForNodeType(nodeType) !== undefined;
}
