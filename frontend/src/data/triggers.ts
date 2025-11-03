import { TriggerOption } from '../types/modal.types';

export const triggerOptions: TriggerOption[] = [
  {
    id: 'webhook',
    name: 'Webhook',
    description: 'Trigger when a webhook receives data',
    icon: 'Webhook',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'schedule',
    name: 'Schedule',
    description: 'Run on a recurring schedule',
    icon: 'Clock',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'human-input',
    name: 'Human Input',
    description: 'Wait for human approval or input',
    icon: 'UserCheck',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'doc-event',
    name: 'Data',
    description: 'Trigger on data events',
    icon: 'Database',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'google-sheets',
    name: 'Google Sheets',
    description: 'Trigger from Google Sheets',
    icon: 'Sheet',
    category: 'popular',
    tab: 'apps'
  },
  {
    id: 'slack',
    name: 'Slack',
    description: 'Trigger from Slack messages',
    icon: 'MessageSquare',
    category: 'popular',
    tab: 'apps'
  },
  {
    id: 'notion',
    name: 'Notion',
    description: 'Trigger from Notion database',
    icon: 'FileText',
    category: 'popular',
    tab: 'apps'
  },
  {
    id: 'gmail',
    name: 'Gmail',
    description: 'Trigger from Gmail emails',
    icon: 'Mail',
    category: 'popular',
    tab: 'apps'
  },
  {
    id: 'hubspot',
    name: 'HubSpot',
    description: 'Trigger from HubSpot CRM',
    icon: 'Database',
    category: 'popular',
    tab: 'apps'
  },
  {
    id: 'calendar',
    name: 'Calendar',
    description: 'Trigger from calendar events',
    icon: 'Calendar',
    category: 'popular',
    tab: 'apps'
  }
];
