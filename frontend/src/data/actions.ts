import { ActionOption } from "../types/modal.types";
import type { ActionType } from "../types/flow.types";
import type { BackendNodeType } from "../services/flowApi";

export const actionOptions: ActionOption[] = [
  // ─── AI & Agents ────────────────────────────────────────────────────
  {
    id: 'agent-run',
    name: 'Run agent',
    description: 'Execute a HUF AI agent',
    icon: 'SquareAsterisk',
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
  {
    id: 'end',
    name: 'End',
    description: 'Finish the flow and return a result',
    icon: 'CheckCircle2',
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
    id: 'state-get',
    name: 'Get state',
    description: 'Read a saved value by key (per flow)',
    icon: 'Database',
    category: 'transform'
  },
  {
    id: 'state-set',
    name: 'Set state',
    description: 'Save a value by key, with optional TTL',
    icon: 'Save',
    category: 'transform'
  },
  {
    id: 'state-delete',
    name: 'Delete state',
    description: 'Remove a saved value by key',
    icon: 'Trash2',
    category: 'transform'
  },
  {
    id: 'doc-create',
    name: 'Create document',
    description: 'Insert a document of an allowed DocType',
    icon: 'FilePlus',
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

/**
 * How each card materialises on the canvas (FIELD_CONTRACT section 2). `configType` is the
 * ActionConfig discriminator; `toolId` presets `tool_id` for the tool.call-based cards.
 * Execute Code has no card: Flows have no execution profile, so run_python cannot run.
 * HTTP Request maps to tool_id `http_request` (tool registration is tracked separately).
 */
export interface ActionCardContract {
  configType: ActionType;
  /** graph-IR node type the card serialises to. */
  backendType: BackendNodeType;
  toolId?: string;
  /** Tool ids the card's tool picker may offer (File / Sheets / Slack). */
  toolIds?: string[];
}

export const ACTION_CARD_CONTRACT: Record<string, ActionCardContract> = {
  'agent-run': { configType: 'agent-run', backendType: 'agent.run' },
  'tool-call': { configType: 'tool-call', backendType: 'tool.call' },
  'router': { configType: 'router', backendType: 'router.llm' },
  'condition': { configType: 'condition', backendType: 'condition' },
  'loop': { configType: 'foreach', backendType: 'foreach' },
  'human.approval': { configType: 'human.approval', backendType: 'human.approval' },
  'transform': { configType: 'transform', backendType: 'transform' },
  'state-get': { configType: 'state-get', backendType: 'state.get' },
  'state-set': { configType: 'state-set', backendType: 'state.set' },
  'state-delete': { configType: 'state-delete', backendType: 'state.delete' },
  'doc-create': { configType: 'doc-create', backendType: 'doc.create' },
  'email': { configType: 'tool-call', backendType: 'tool.call', toolId: 'gmail_send_email' },
  'http-request': { configType: 'tool-call', backendType: 'tool.call', toolId: 'http_request' },
  'file': {
    configType: 'tool-call', backendType: 'tool.call', toolId: 'gdrive_list_files',
    toolIds: ['gdrive_list_files', 'gdrive_search_files', 'gdrive_get_file'],
  },
  'slack': {
    configType: 'tool-call', backendType: 'tool.call', toolId: 'slack_send_message',
    toolIds: ['slack_send_message', 'slack_send_thread_reply'],
  },
  'sheets': {
    configType: 'tool-call', backendType: 'tool.call', toolId: 'gsheets_read',
    toolIds: ['gsheets_read', 'gsheets_update', 'gsheets_create'],
  },
};
