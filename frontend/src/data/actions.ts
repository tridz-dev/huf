import { ActionOption } from '../types/modal.types';

export const actionOptions: ActionOption[] = [
  {
    id: 'transform',
    name: 'Transform Data',
    description: 'Transform and map data fields',
    icon: 'Repeat',
    category: 'transform'
  },
  {
    id: 'router',
    name: 'Router',
    description: 'Split flow into branches with conditions',
    icon: 'GitBranch',
    category: 'control'
  },
  {
    id: 'loop',
    name: 'Loop',
    description: 'Iterate over array data',
    icon: 'RotateCw',
    category: 'control'
  },
  {
    id: 'human-in-loop',
    name: 'Human in Loop',
    description: 'Request human approval',
    icon: 'UserCheck',
    category: 'control'
  },
  {
    id: 'code',
    name: 'Execute Code',
    description: 'Run custom JavaScript/Python code',
    icon: 'Code',
    category: 'transform'
  },
  {
    id: 'email',
    name: 'Send Email',
    description: 'Send an email message',
    icon: 'Mail',
    category: 'utility'
  },
  {
    id: 'webhook',
    name: 'Call Webhook',
    description: 'Make HTTP request to webhook',
    icon: 'Webhook',
    category: 'utility'
  },
  {
    id: 'file',
    name: 'File Operations',
    description: 'Read, write, or delete files',
    icon: 'FileText',
    category: 'utility'
  },
  {
    id: 'date',
    name: 'Date Utility',
    description: 'Format or manipulate dates',
    icon: 'Calendar',
    category: 'utility'
  },
  {
    id: 'slack',
    name: 'Slack',
    description: 'Send Slack messages',
    icon: 'MessageSquare',
    category: 'integration'
  },
  {
    id: 'sheets',
    name: 'Google Sheets',
    description: 'Update Google Sheets',
    icon: 'Sheet',
    category: 'integration'
  },
  {
    id: 'notion',
    name: 'Notion',
    description: 'Create or update Notion pages',
    icon: 'FileText',
    category: 'integration'
  }
];
