import { TriggerOption } from '../types/modal.types';

export const triggerOptions: TriggerOption[] = [
  {
    id: 'webhook',
    name: 'Webhook',
    description: 'Starts when another system calls its address.',
    icon: 'Webhook',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'schedule',
    name: 'Schedule',
    description: 'Starts by itself at times you choose.',
    icon: 'Clock',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'doc-event',
    name: 'Record change',
    description: 'Starts when a record is added, changed or deleted.',
    icon: 'Database',
    category: 'highlight',
    tab: 'explore'
  }
];
