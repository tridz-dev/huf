import { ActionOption } from "../types/modal.types";
import type { ActionType } from "../types/flow.types";
import type { BackendNodeType } from "../services/flowApi";

/**
 * The step palette. `name` is also the title a new card gets on the canvas and in the sidebar, so it is written as
 * a plain phrase. `description` is one short line about what the step does. `keywords` only widen search (old and
 * technical words people may still type); they are never shown.
 */
export const actionOptions: ActionOption[] = [
  // ─── AI ─────────────────────────────────────────────────────────────
  {
    id: 'agent-run',
    name: 'Run agent',
    description: 'Give an AI agent a task and use its answer.',
    icon: 'SquareAsterisk',
    category: 'agent',
    keywords: ['ai', 'assistant', 'llm', 'prompt'],
  },
  {
    id: 'router',
    name: 'Choose with AI',
    description: 'Let an AI pick which path to follow.',
    icon: 'GitBranch',
    category: 'agent',
    keywords: ['router', 'llm router', 'decide', 'path', 'ai'],
  },

  // ─── Decisions and loops ────────────────────────────────────────────
  {
    id: 'condition',
    name: 'If / else',
    description: 'Go one of two ways, based on your data.',
    icon: 'GitFork',
    category: 'control',
    keywords: ['condition', 'if', 'else', 'check', 'true', 'false', 'yes', 'no'],
  },
  {
    id: 'loop',
    name: 'Repeat for each item',
    description: 'Run some steps once for every item in a list.',
    icon: 'RotateCw',
    category: 'control',
    keywords: ['loop', 'foreach', 'each', 'list', 'repeat'],
  },
  {
    id: 'end',
    name: 'Finish',
    description: 'Ends the flow and gives back a result.',
    icon: 'Flag',
    category: 'control',
    keywords: ['end', 'stop', 'result', 'done'],
  },

  // ─── People ─────────────────────────────────────────────────────────
  {
    id: 'human.approval',
    name: 'Wait for approval',
    description: 'Pause until a person approves or rejects.',
    icon: 'UserCheck',
    category: 'people',
    keywords: ['human', 'human in loop', 'approve', 'reject', 'review', 'person'],
  },

  // ─── Work with data ─────────────────────────────────────────────────
  {
    id: 'transform',
    name: 'Change data',
    description: 'Change text, lists or records, without AI.',
    icon: 'Repeat',
    category: 'data',
    keywords: ['transform', 'text', 'filter', 'sort', 'join', 'concatenate', 'regex', 'lowercase', 'uppercase'],
  },
  {
    id: 'state-set',
    name: 'Save data for later',
    description: 'Remember a value for later steps or runs.',
    icon: 'Save',
    category: 'data',
    keywords: ['state', 'set state', 'store', 'remember', 'variable'],
  },
  {
    id: 'state-get',
    name: 'Look up saved data',
    description: 'Read a value this flow saved earlier.',
    icon: 'ArchiveRestore',
    category: 'data',
    keywords: ['state', 'get state', 'read', 'recall', 'variable'],
  },
  {
    id: 'state-delete',
    name: 'Forget saved data',
    description: 'Remove a value this flow saved earlier.',
    icon: 'ArchiveX',
    category: 'data',
    keywords: ['state', 'delete state', 'remove', 'clear'],
  },
  {
    id: 'doc-create',
    name: 'Create a record',
    description: 'Add a new record, such as a ToDo.',
    icon: 'FilePlus',
    category: 'data',
    keywords: ['document', 'create document', 'doctype', 'insert', 'todo'],
  },

  // ─── Apps ───────────────────────────────────────────────────────────
  {
    id: 'slack',
    name: 'Slack',
    description: 'Post a message to a Slack channel.',
    icon: 'MessageSquare',
    category: 'apps',
    keywords: ['message', 'chat', 'channel', 'notify'],
  },
  {
    id: 'email',
    name: 'Send email',
    description: 'Send an email from your Gmail.',
    icon: 'Mail',
    category: 'apps',
    keywords: ['gmail', 'mail', 'message', 'notify'],
  },
  {
    id: 'sheets',
    name: 'Google Sheets',
    description: 'Read, update or create a spreadsheet.',
    icon: 'Sheet',
    category: 'apps',
    keywords: ['spreadsheet', 'google', 'excel', 'rows'],
  },
  {
    id: 'file',
    name: 'Google Drive files',
    description: 'List, search or get files in Google Drive.',
    icon: 'FileText',
    category: 'apps',
    keywords: ['drive', 'file operations', 'files', 'google', 'documents'],
  },
  {
    id: 'tool-call',
    name: 'Do something in an app',
    description: 'Pick any action from a connected app.',
    icon: 'Wrench',
    category: 'apps',
    keywords: ['call tool', 'tool', 'action', 'mcp', 'integration'],
  },

  // ─── Advanced ───────────────────────────────────────────────────────
  {
    id: 'http-request',
    name: 'Web request',
    description: 'Call a web address and use the answer.',
    icon: 'Globe',
    category: 'advanced',
    keywords: ['http', 'http request', 'api', 'rest', 'url', 'fetch', 'get', 'post'],
  },
  {
    id: 'code-run',
    name: 'Run Python code',
    description: 'Run a short Python snippet in a safe sandbox.',
    icon: 'Terminal',
    category: 'advanced',
    keywords: ['execute code', 'code', 'script', 'python'],
  },
];

/** Section titles of the palette, in order. Category ids stay internal. */
export const ACTION_SECTIONS: Array<{ category: ActionOption['category']; title: string }> = [
  { category: 'agent', title: 'AI' },
  { category: 'control', title: 'Decide and repeat' },
  { category: 'people', title: 'People' },
  { category: 'data', title: 'Work with data' },
  { category: 'apps', title: 'Apps' },
  { category: 'advanced', title: 'Advanced' },
];

/**
 * How each card materialises on the canvas (FIELD_CONTRACT section 2). `configType` is the
 * ActionConfig discriminator; `toolId` presets `tool_id` for the tool.call-based cards.
 * Execute code (`code-run`, graph-IR `code.run`) is its own node type, not a tool call; its card is only offered
 * while the server says code may run in Flows and the user holds flows.execute_code (see lib/codeFlow.ts).
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
  'code-run': { configType: 'code-run', backendType: 'code.run' },
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
