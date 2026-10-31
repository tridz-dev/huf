import { TriggerOption } from '../types/modal.types';

export const triggerOptions: TriggerOption[] = [
  {
    id: 'webhook',
    name: 'Webhook',
    description: 'Starts when another app sends a request to its web address.',
    icon: 'Webhook',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'schedule',
    name: 'Schedule',
    description: 'Starts by itself at times you choose, like every weekday at 9.',
    icon: 'Clock',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'doc-event',
    name: 'When a document changes',
    nodeTitle: 'Document change',
    description: 'Starts when something is added, changed or deleted in your data, like a new customer.',
    icon: 'Database',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'gateway',
    name: 'A chat message',
    nodeTitle: 'Chat message',
    description: 'Starts when someone sends a message to one of your connected chat channels.',
    icon: 'MessageSquare',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'whatsapp',
    name: 'A WhatsApp message',
    nodeTitle: 'WhatsApp message',
    description: 'Starts when someone sends a message to one of your WhatsApp numbers.',
    icon: 'MessageCircle',
    category: 'highlight',
    tab: 'explore'
  },
  {
    id: 'telegram',
    name: 'A Telegram message',
    nodeTitle: 'Telegram message',
    description: 'Starts when someone sends a message to one of your Telegram bots.',
    icon: 'Send',
    category: 'highlight',
    tab: 'explore'
  }
];
