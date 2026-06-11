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
  }
];
