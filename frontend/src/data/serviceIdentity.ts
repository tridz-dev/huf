import { createElement } from 'react';
import type { ComponentType } from 'react';
import { Workflow } from 'lucide-react';
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

// Official icon-only mark from SerpApi's media kit. It is kept inline so the
// integration catalog never depends on a third-party image host at runtime.
const SerpApiIcon: ServiceIcon = ({ className }) =>
  createElement(
    'svg',
    {
      className,
      viewBox: '0 0 726.54 726.54',
      fill: 'none',
      'aria-hidden': true,
    },
    createElement('path', {
      d: 'm 141.299,530.374 c 8.977,31.839 35.67,56.769 69.397,64.614 V 726.54 H 208.88 C 97.7879,726.54 6.95296,639.815 0.381836,530.374 Z m 69.397,-398.823 c -41.703,9.701 -72.653,45.522 -72.653,88.227 0,50.157 42.693,90.818 95.358,90.818 52.665,0 95.359,-40.661 95.359,-90.818 0,-42.705 -30.951,-78.526 -72.655,-88.227 V 0 H 517.66 C 629.366,0 720.592,87.6865 726.261,197.982 H 583.916 c -10.25,-39.63 -47.818,-69.021 -92.594,-69.021 -52.665,0 -95.358,40.66 -95.358,90.817 0,42.706 30.951,78.526 72.654,88.227 v 110.529 c -41.703,9.701 -72.654,45.522 -72.654,88.228 0,42.705 30.951,78.526 72.654,88.226 V 726.54 H 256.105 V 594.988 c 41.704,-9.701 72.655,-45.521 72.655,-88.226 0,-50.157 -42.694,-90.817 -95.359,-90.818 -44.776,0 -82.343,29.392 -92.593,69.022 H 0 V 208.88 C 0,93.5188 93.5188,0 208.88,0 h 1.816 z M 726.54,517.66 c 0,115.361 -93.519,208.88 -208.88,208.88 h -3.633 V 594.988 c 41.703,-9.701 72.654,-45.521 72.654,-88.226 0,-42.706 -30.95,-78.527 -72.654,-88.228 V 308.005 c 33.728,-7.846 60.421,-32.775 69.398,-64.614 H 726.54 Z',
      fill: 'url(#serpapi-brand-gradient)',
    }),
    createElement(
      'defs',
      null,
      createElement(
        'linearGradient',
        {
          id: 'serpapi-brand-gradient',
          x1: '73.5622',
          y1: '719.275',
          x2: '653.886',
          y2: '63.5722',
          gradientUnits: 'userSpaceOnUse',
        },
        createElement('stop', { stopColor: '#377FEA' }),
        createElement('stop', { offset: '1', stopColor: '#8C45EF' }),
      ),
    ),
  );

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
  serpapi: { title: 'SerpApi', icon: SerpApiIcon },
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
