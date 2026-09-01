import { ActionOption } from "../types/modal.types";

export const actionOptions: ActionOption[] = [
  // ─── AI & Agents ────────────────────────────────────────────────────
  {
    id: 'agent-run',
    name: 'Run agent',
    description: 'Execute a HUF AI agent',
    icon: 'Bot',
    category: 'agent'
  },

  // ─── Tools ──────────────────────────────────────────────────────────
  {
    id: 'tool-call',
    name: 'Call tool',
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
    name: 'Transform data',
    description: 'Map and transform data fields',
    icon: 'Repeat',
    category: 'transform'
  },
  {
    id: 'code',
    name: 'Execute code',
    description: 'Run custom code snippet',
    icon: 'Code',
    category: 'transform'
  },

  // ─── Utilities ──────────────────────────────────────────────────────
  {
    id: 'email',
    name: 'Send email',
    description: 'Send an email notification',
    icon: 'Mail',
    category: 'utility'
  },
  {
    id: 'http-request',
    name: 'HTTP Request',
    description: 'Make an HTTP request to any URL',
    icon: 'Globe',
    category: 'utility'
  },
  {
    id: 'http-request',
    name: 'HTTP Request',
    description: 'Make an HTTP request to any URL',
    icon: 'Globe',
    category: 'utility'
  },
  {
    id: 'file',
    name: 'File operations',
    description: 'List, search, or read files in Google Drive',
    icon: 'FileText',
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
];
