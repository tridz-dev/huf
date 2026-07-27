import type { ComponentType } from 'react';
import { Search, Workflow } from 'lucide-react';
import { FaMicrosoft, FaSlack } from 'react-icons/fa';
import {
  SiDiscord,
  SiGithub,
  SiGmail,
  SiGooglecalendar,
  SiGoogledrive,
  SiGooglemaps,
  SiGooglemeet,
  SiGooglesheets,
  SiJira,
  SiTelegram,
  SiVk,
  SiWechat,
  SiWhatsapp,
} from 'react-icons/si';

export type ServiceIcon = ComponentType<{ className?: string }>;

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

const serviceIdentities: Record<string, { title: string; icon: ServiceIcon }> = {
  telegram: { title: 'Telegram', icon: SiTelegram },
  slack: { title: 'Slack', icon: FaSlack },
  whatsapp: { title: 'WhatsApp', icon: SiWhatsapp },
  discord: { title: 'Discord', icon: SiDiscord },
  microsoft_teams: { title: 'Microsoft Teams', icon: FaMicrosoft },
  teams: { title: 'Microsoft Teams', icon: FaMicrosoft },
  wecom: { title: 'WeCom', icon: SiWechat },
  vk: { title: 'VK', icon: SiVk },
  github: { title: 'GitHub', icon: SiGithub },
  jira: { title: 'Jira', icon: SiJira },
  gmail: { title: 'Gmail', icon: SiGmail },
  google_calendar: { title: 'Google Calendar', icon: SiGooglecalendar },
  google_drive: { title: 'Google Drive', icon: SiGoogledrive },
  google_sheets: { title: 'Google Sheets', icon: SiGooglesheets },
  google_maps: { title: 'Google Maps', icon: SiGooglemaps },
  google_meet: { title: 'Google Meet', icon: SiGooglemeet },
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
