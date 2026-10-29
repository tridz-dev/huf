import { Activity, ChartLine, FileText, House, Megaphone, Phone, Plug, Settings, Workflow, type LucideIcon } from 'lucide-react';

export interface ChannelSection {
  key: string;
  label: string;
  /** Path segment under `n/:gw/`. */
  path: string;
  icon: LucideIcon;
}

export const CHANNEL_SECTIONS: ChannelSection[] = [
  { key: 'home', label: 'Home', path: 'home', icon: House },
  { key: 'activity', label: 'Activity', path: 'activity', icon: Activity },
  { key: 'broadcasts', label: 'Broadcasts', path: 'broadcasts', icon: Megaphone },
  { key: 'templates', label: 'Templates', path: 'templates', icon: FileText },
  { key: 'automations', label: 'Automations', path: 'automations', icon: Workflow },
  { key: 'analytics', label: 'Analytics', path: 'analytics', icon: ChartLine },
  { key: 'connections', label: 'Connections', path: 'connections', icon: Plug },
  { key: 'numbers', label: 'Numbers', path: 'numbers', icon: Phone },
  { key: 'settings', label: 'Settings', path: 'settings', icon: Settings },
];

/** Numbers is gateway-less at /channels/whatsapp/numbers; the rest live under n/:gw/. */
export function sectionHref(section: ChannelSection, gateway: string | undefined): string {
  if (!gateway) return `/channels/whatsapp/${section.key === 'numbers' ? 'numbers' : 'setup'}`;
  return `/channels/whatsapp/n/${encodeURIComponent(gateway)}/${section.path}`;
}

export function sectionFromPath(pathname: string): ChannelSection | undefined {
  const parts = pathname.replace(/^\/channels\/whatsapp\/?/, '').split('/').filter(Boolean);
  const seg = parts[0] === 'n' ? parts[2] : parts[0];
  return CHANNEL_SECTIONS.find((s) => s.path === seg);
}
