import { Activity, ChartLine, FileText, House, Megaphone, Phone, Plug, Settings, ShoppingBag, Workflow, type LucideIcon } from 'lucide-react';
import { channelMeta } from './channelsMeta';

export interface ChannelSection {
  key: string;
  label: string;
  /** Path segment under `n/:gw/`. */
  path: string;
  icon: LucideIcon;
  /** WhatsApp-only (hidden for other channels). */
  whatsappOnly?: boolean;
}

export const CHANNEL_SECTIONS: ChannelSection[] = [
  { key: 'home', label: 'Home', path: 'home', icon: House },
  { key: 'activity', label: 'Activity', path: 'activity', icon: Activity },
  { key: 'broadcasts', label: 'Broadcasts', path: 'broadcasts', icon: Megaphone, whatsappOnly: true },
  { key: 'templates', label: 'Templates', path: 'templates', icon: FileText, whatsappOnly: true },
  { key: 'commerce', label: 'Commerce', path: 'commerce', icon: ShoppingBag, whatsappOnly: true },
  { key: 'automations', label: 'Automations', path: 'automations', icon: Workflow },
  { key: 'analytics', label: 'Analytics', path: 'analytics', icon: ChartLine },
  { key: 'connections', label: 'Connections', path: 'connections', icon: Plug },
  { key: 'numbers', label: 'Numbers', path: 'numbers', icon: Phone },
  { key: 'settings', label: 'Settings', path: 'settings', icon: Settings },
];

/** Sections that apply to a channel; the gateway list is named per channel (Numbers/Bots/Workspaces). */
export function sectionsFor(channel: string = 'whatsapp'): ChannelSection[] {
  const meta = channelMeta(channel);
  return CHANNEL_SECTIONS.filter((s) => meta.key === 'whatsapp' || !s.whatsappOnly).map((s) =>
    s.key === 'numbers' ? { ...s, label: meta.noun } : s
  );
}

/** Numbers is gateway-less at /channels/:channel/numbers; the rest live under n/:gw/. */
export function sectionHref(section: ChannelSection, gateway: string | undefined, channel: string = 'whatsapp'): string {
  if (!gateway) return `/channels/${channel}/${section.key === 'numbers' ? 'numbers' : 'setup'}`;
  return `/channels/${channel}/n/${encodeURIComponent(gateway)}/${section.path}`;
}

export function sectionFromPath(pathname: string): ChannelSection | undefined {
  const m = pathname.match(/^\/channels\/([^/]+)\/?(.*)$/);
  const channel = m?.[1] ?? 'whatsapp';
  const parts = (m?.[2] ?? '').split('/').filter(Boolean);
  const seg = parts[0] === 'n' ? parts[2] : parts[0];
  return sectionsFor(channel).find((s) => s.path === seg);
}
