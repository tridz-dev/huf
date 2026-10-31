import type { GatewayChoice } from './gatewayTrigger.types';
import { GATEWAY_TRIGGER_KINDS } from './triggerKinds';

/** The id of an editor-side chat trigger kind. */
export type GatewayKindId = (typeof GATEWAY_TRIGGER_KINDS)[number]['id'];

export const isGatewayKindId = (id: unknown): id is GatewayKindId =>
  typeof id === 'string' && GATEWAY_TRIGGER_KINDS.some((k) => k.id === id);

const kindOf = (id: GatewayKindId) => GATEWAY_TRIGGER_KINDS.find((k) => k.id === id)!;

/** What the thing to pick is called: never "gateway" or "provider". */
export function channelNoun(id: GatewayKindId): string {
  return id === 'whatsapp' ? 'WhatsApp number' : id === 'telegram' ? 'Telegram bot' : 'channel';
}

/** The one wording of the "connect one" link, on the picker card and in the form. */
export const connectWords = (id: GatewayKindId): string => (id === 'telegram' ? 'Connect a bot' : id === 'whatsapp' ? 'Connect a number' : 'Connect a channel');

/** "Pick a WhatsApp number" / "Pick a Telegram bot" / "Pick a channel". */
export const pickPrompt = (id: GatewayKindId): string => `Pick a ${channelNoun(id)}`;

/** Gateways a person may choose for this kind: enabled or not, but of the right provider. */
export function gatewaysForKind(id: GatewayKindId, gateways: readonly GatewayChoice[]): GatewayChoice[] {
  const provider = kindOf(id).provider;
  return gateways.filter((g) => !provider || g.provider === provider);
}

/** The name people know a channel by: its label when the registry has it, else the stored name. */
export function gatewayDisplayName(name: string | undefined, gateways: readonly GatewayChoice[] | null | undefined): string {
  if (!name) return '';
  return gateways?.find((g) => g.name === name)?.label || name;
}

/** "WhatsApp", "Telegram", or the channel's own kind for the generic trigger ("Slack"); '' when unknown. */
export function channelWord(id: GatewayKindId, name: string | undefined, gateways: readonly GatewayChoice[] | null | undefined): string {
  const fixed = kindOf(id).provider ? kindOf(id).channelWord : '';
  return fixed || gateways?.find((g) => g.name === name)?.provider || '';
}

/** Short name of the step ("WhatsApp message"), used as the card title and in the data picker ("Trigger: WhatsApp message"). */
export const NODE_TITLE: Record<GatewayKindId, string> = {
  gateway: 'Chat message',
  whatsapp: 'WhatsApp message',
  telegram: 'Telegram message',
};
