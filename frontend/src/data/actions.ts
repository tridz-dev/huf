import { ActionOption } from '../types/modal.types';

export const actionOptions: ActionOption[] = [
  {
    id: 'agent-run',
    name: 'Run Agent',
    description: 'Execute a HUF AI agent',
    icon: 'Bot',
    category: 'transform'
  },
  {
    id: 'tool-call',
    name: 'Call Tool',
    description: 'Execute a tool function',
    icon: 'Wrench',
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
    id: 'human-in-loop',
    name: 'Human in Loop',
    description: 'Request human approval',
    icon: 'UserCheck',
    category: 'control'
  }
];
