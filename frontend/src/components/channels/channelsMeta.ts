import { Send, Slack, Users, MessageCircle, type LucideIcon } from 'lucide-react';

export type ChannelKey = 'whatsapp' | 'telegram' | 'slack' | 'teams';

export interface ChannelMeta {
  key: ChannelKey;
  label: string;
  icon: LucideIcon;
  /** What a gateway is called in this channel ("Numbers", "Bots", "Workspaces"). */
  noun: string;
  nounSingular: string;
  /** Existing per-provider page used for connecting and managing credentials. */
  setupHref: string;
}

export const CHANNELS: ChannelMeta[] = [
  { key: 'whatsapp', label: 'WhatsApp', icon: MessageCircle, noun: 'Numbers', nounSingular: 'number', setupHref: '/channels/whatsapp/setup' },
  { key: 'telegram', label: 'Telegram', icon: Send, noun: 'Bots', nounSingular: 'bot', setupHref: '/telegram' },
  { key: 'slack', label: 'Slack', icon: Slack, noun: 'Workspaces', nounSingular: 'workspace', setupHref: '/gateways' },
  { key: 'teams', label: 'Teams', icon: Users, noun: 'Workspaces', nounSingular: 'workspace', setupHref: '/gateways' },
];

export const CHANNEL_KEYS = CHANNELS.map((c) => c.key);

export function isChannelKey(v: string | undefined): v is ChannelKey {
  return !!v && (CHANNEL_KEYS as string[]).includes(v);
}

export function channelMeta(key: string | undefined): ChannelMeta {
  return CHANNELS.find((c) => c.key === key) ?? CHANNELS[0];
}

/** Existing generic gateway detail page (credentials, webhook) for a non-WhatsApp gateway. */
export const gatewayDetailHref = (name: string) => `/gateways/${encodeURIComponent(name)}`;

/** WhatsApp is always reachable (its setup lives in the shell); others need at least one gateway. */
export const channelEnabled = (key: string, count: number) => key === 'whatsapp' || count > 0;
