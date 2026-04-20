import { ActionOption } from "../types/modal.types";

export const actionOptions: ActionOption[] = [
  // ─── AI & Agents ────────────────────────────────────────────────────
  {
    id: 'agent-run',
    name: 'Run Agent',
    description: 'Execute a HUF AI agent',
    icon: 'Bot',
    category: 'agent'
  },

  // ─── Tools ──────────────────────────────────────────────────────────
  {
    id: 'tool-call',
    name: 'Call Tool',
    description: 'Execute a tool function',
    icon: 'Wrench',
    category: 'tool'
  },

  // ─── Control Flow ───────────────────────────────────────────────────
  {
    id: 'router',
    name: 'LLM Router',
    description: 'Intelligently route based on AI analysis',
    icon: 'GitBranch',
    category: 'control'
  },
  {
    id: 'condition',
    name: 'Condition (If/Else)',
    description: 'Branch flow based on data',
    icon: 'GitBranch',
    category: 'control'
  },
  {
    id: "loop",
    name: "Loop",
    description: "Iterate over array data",
    icon: "RotateCw",
    category: "control",
  },
  {
    id: 'human.approval',
    name: 'Human in Loop',
    description: 'Request human approval',
    icon: 'UserCheck',
    category: 'control'
  },

  // ─── Transform ──────────────────────────────────────────────────────
  {
    id: 'transform',
    name: 'Transform Data',
    description: 'Map and transform data fields',
    icon: 'Repeat',
    category: 'transform'
  },
  {
    id: 'code',
    name: 'Execute Code',
    description: 'Run custom code snippet',
    icon: 'Code',
    category: 'transform'
  },

  // ─── Utilities ──────────────────────────────────────────────────────
  {
    id: 'email',
    name: 'Send Email',
    description: 'Send an email notification',
    icon: 'Mail',
    category: 'utility'
  },
  {
    id: 'webhook',
    name: 'Call Webhook',
    description: 'Make an HTTP request',
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
    description: 'Format and manipulate dates',
    icon: 'Calendar',
    category: 'utility'
  },

  // ─── Integrations ──────────────────────────────────────────────────
  {
    id: 'slack',
    name: 'Slack',
    description: 'Send messages to Slack',
    icon: 'MessageSquare',
    category: 'integration'
  },
  {
    id: 'sheets',
    name: 'Google Sheets',
    description: 'Read or write spreadsheet data',
    icon: 'Sheet',
    category: 'integration'
  },
  {
    id: 'notion',
    name: 'Notion',
    description: 'Create or update Notion pages',
    icon: 'FileText',
    category: 'integration'
  },
];
