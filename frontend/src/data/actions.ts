import { ActionOption } from '../types/modal.types';

/**
 * Action options — only includes node types with real backend executors.
 * Ghost nodes (code, email, file, date, webhook utility) have been removed.
 */
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
    id: 'condition',
    name: 'Condition (IF)',
    description: 'Branch flow with True/False logic',
    icon: 'GitBranch',
    category: 'control'
  },
  {
    id: 'router',
    name: 'LLM Router',
    description: 'Route flow using AI decision',
    icon: 'GitBranch',
    category: 'control'
  },
  {
    id: 'human-in-loop',
    name: 'Human Approval',
    description: 'Request human approval',
    icon: 'UserCheck',
    category: 'control'
  },
  {
    id: 'loop',
    name: 'Loop',
    description: 'Iterate over a list of items',
    icon: 'RotateCw',
    category: 'control'
  },
  {
    id: 'http-request',
    name: 'HTTP Request',
    description: 'Call an external API',
    icon: 'Globe',
    category: 'integration'
  },
  {
    id: 'transform',
    name: 'Transform Data',
    description: 'Map and reshape context data',
    icon: 'Repeat',
    category: 'transform'
  }
];
