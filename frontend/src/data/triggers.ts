import { TriggerOption } from '../types/modal.types';

export const triggerOptions: TriggerOption[] = [
  {
    id: 'webhook',
    name: 'Webhook',
    description: 'Starts the flow when another system sends a request to its web address.',
    icon: 'Webhook',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'schedule',
    name: 'Schedule',
    description: 'Starts the flow by itself at times you choose, such as every morning.',
    icon: 'Clock',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'doc-event',
    name: 'Data',
    description: 'Starts the flow when a record is created, changed or deleted.',
    icon: 'Database',
    category: 'highlight',
    tab: 'explore'
  }
];
