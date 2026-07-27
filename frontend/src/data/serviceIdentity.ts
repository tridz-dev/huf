import {
  Bot,
  CalendarDays,
  Folder,
  Github,
  LucideIcon,
  Mail,
  Map,
  MessageCircle,
  PanelsTopLeft,
  Search,
  Send,
  Slack,
  Table2,
  Video,
  Workflow,
} from 'lucide-react';

export const messagingServiceNames = new Set([
  'telegram',
  'slack',
  'whatsapp',
  'discord',
  'microsoft_teams',
  'teams',
  'wecom',
  'vk',
]);

const serviceIdentities: Record<string, { title: string; icon: LucideIcon }> = {
  telegram: { title: 'Telegram', icon: Send },
  slack: { title: 'Slack', icon: Slack },
  whatsapp: { title: 'WhatsApp', icon: MessageCircle },
  discord: { title: 'Discord', icon: Bot },
  microsoft_teams: { title: 'Microsoft Teams', icon: Video },
  teams: { title: 'Microsoft Teams', icon: Video },
  wecom: { title: 'WeCom', icon: MessageCircle },
  vk: { title: 'VK', icon: MessageCircle },
  github: { title: 'GitHub', icon: Github },
  jira: { title: 'Jira', icon: PanelsTopLeft },
  gmail: { title: 'Gmail', icon: Mail },
  google_calendar: { title: 'Google Calendar', icon: CalendarDays },
  google_drive: { title: 'Google Drive', icon: Folder },
  google_sheets: { title: 'Google Sheets', icon: Table2 },
  google_maps: { title: 'Google Maps', icon: Map },
  google_meet: { title: 'Google Meet', icon: Video },
  serpapi: { title: 'SerpApi', icon: Search },
};

export function getServiceIdentity(serviceName: string | null | undefined) {
  const normalized = (serviceName || '').trim().toLowerCase();
  return serviceIdentities[normalized] ?? {
    title: normalized
      .split('_')
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ') || 'Integration',
    icon: Workflow,
  };
}
