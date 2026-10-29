/**
 * Plain-language, per-field validation for the Flow builder. Mirrors the required fields of
 * docs/flow/FIELD_CONTRACT.md so a user sees "Choose an agent" next to the field instead of a raw
 * JSON-schema error after Save. Field names are the contract's config keys.
 */
import { getTransformOp } from './flowTransformOps';
import { transformParamHelp } from './flowHelp';
import { branchHandlesFor } from './flowBranches';
import { cronProblem } from './flowSchedule';
import { secretProblem } from './flowWebhookUi';
import { requiredInputsFor } from './flowToolSchemas';
import { edgeRoute } from '../services/flowSerializer';
import { unreachableNodeIds } from './flowEdit';
import { MAX_CODE_BYTES } from './codeFlow';
import type { FlowEdge, FlowNode } from '../types/flow.types';

/** Id of the "Can't save yet" / "Finish setting up" toast, so the next edit or selection can dismiss it. */
export const BLOCKED_TOAST_ID = 'flow-blocked';

type Cfg = Record<string, unknown>;

export interface NodeLike {
  id: string;
  data: { label?: string; nodeType?: string; triggerConfig?: unknown; actionConfig?: unknown };
}
export type EdgeLike = Pick<FlowEdge, 'source' | 'target' | 'sourceHandle' | 'label' | 'data'>;

export interface FlowIssue {
  nodeId: string;
  nodeLabel: string;
  /** Contract node type, used in test ids (`flow-error-<kind>-<field>`). */
  kind: string;
  field: string;
  message: string;
}

export const isBlank = (v: unknown): boolean =>
  v == null || (typeof v === 'string' && v.trim() === '') || (Array.isArray(v) && v.length === 0);

/** Contract node type for a node as the builder holds it. */
export function nodeKind(node: NodeLike): string {
  const d = node.data;
  if (d.nodeType === 'end') return 'output';
  if (d.nodeType === 'trigger') {
    const t = (d.triggerConfig as Cfg | undefined)?.type;
    return t === 'webhook' ? 'trigger.webhook' : t === 'schedule' ? 'trigger.schedule' : t === 'doc-event' ? 'trigger.doc-event' : 'trigger.unset';
  }
  const t = (d.actionConfig as Cfg | undefined)?.type;
  switch (t) {
    case 'agent-run': return 'agent.run';
    case 'tool-call': return 'tool.call';
    case 'router': return 'router.llm';
    case 'condition': return 'condition';
    case 'foreach': return 'foreach';
    case 'human.approval': return 'human.approval';
    case 'transform': return 'transform';
    case 'state-get': return 'state.get';
    case 'state-set': return 'state.set';
    case 'state-delete': return 'state.delete';
    case 'doc-create': return 'doc.create';
    case 'code-run': return 'code.run';
    default: return typeof t === 'string' ? t : 'unknown';
  }
}

/** Required `input` keys per preset tool (contract section 2). */
export const TOOL_REQUIRED_INPUT: Record<string, Array<[key: string, message: string]>> = {
  gmail_send_email: [['to', 'Enter who the email goes to.'], ['subject', 'Enter a subject.'], ['body', 'Enter the email body.']],
  slack_send_message: [['channel', 'Enter a Slack channel.'], ['text', 'Enter the message text.']],
  slack_send_thread_reply: [['channel', 'Enter a Slack channel.'], ['thread_ts', 'Enter the thread to reply to.'], ['text', 'Enter the message text.']],
  gsheets_read: [['spreadsheet_id', 'Enter the spreadsheet ID.']],
  gsheets_update: [['spreadsheet_id', 'Enter the spreadsheet ID.'], ['range', 'Enter the cell range.'], ['data', 'Enter the data to write.']],
  gsheets_create: [['title', 'Enter a title for the new spreadsheet.']],
  gdrive_search_files: [['query', 'Enter what to search for.']],
  gdrive_get_file: [['file_id', 'Enter the file ID.']],
  http_request: [['url', 'Enter the URL to call.']],
};

/**
 * Problem with a "To"-style address list, or null when fine. Several addresses may be separated by commas or
 * semicolons; an entry containing a `{...}` reference is filled in at run time and not checked. Values that are
 * not plain text (a reference to earlier data) are not checked either.
 */
export function recipientProblem(value: unknown): string | null {
  if (typeof value !== 'string' || value.trim() === '') return null;
  const entries = value.split(/[;,]/).map((e) => e.trim()).filter(Boolean);
  const bad = entries.filter((e) => {
    if (/\{[^}]*\}/.test(e)) return false;
    const addr = /<([^<>]+)>\s*$/.exec(e)?.[1] ?? e;
    return !/^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$/.test(addr);
  });
  if (bad.length === 0) return null;
  return bad.length === 1 && entries.length === 1
    ? 'Enter a valid email address, like name@example.com.'
    : `"${bad[0]}" is not a valid email address. Separate several addresses with commas.`;
}

const asObj = (v: unknown): Cfg => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Cfg) : {});

function refProblem(v: unknown): boolean {
  const from = asObj(v)['$from'];
  return typeof from !== 'string' || from.trim() === '';
}

export function validateNode(node: NodeLike, edges: EdgeLike[]): FlowIssue[] {
  const kind = nodeKind(node);
  const label = node.data.label || kind;
  const issues: FlowIssue[] = [];
  const add = (field: string, message: string) => issues.push({ nodeId: node.id, nodeLabel: label, kind, field, message });
  const out = edges.filter((e) => e.source === node.id);

  if (node.data.nodeType === 'trigger') {
    const c = asObj(node.data.triggerConfig);
    if (kind === 'trigger.unset') add('type', 'Choose how this flow starts.');
    if (kind === 'trigger.webhook') {
      if (c.method !== 'GET' && c.method !== 'POST') add('method', 'Choose GET or POST.');
      const p = secretProblem(c.secret);
      if (p) add('secret', p);
    }
    if (kind === 'trigger.schedule') {
      const p = cronProblem(c.cron as string | undefined);
      if (p) add('cron', p);
    }
    if (kind === 'trigger.doc-event') {
      if (isBlank(c.doctype)) add('doctype', 'Choose a document type.');
      if (isBlank(c.event)) add('event', 'Choose when it should fire.');
    }
    return issues;
  }
  if (node.data.nodeType === 'end') return issues;

  const c = asObj(node.data.actionConfig);
  switch (kind) {
    case 'agent.run':
      if (isBlank(c.agent)) add('agent', 'Choose an agent.');
      if (isBlank(c.prompt)) add('prompt', 'Write the prompt the agent should receive.');
      break;
    case 'tool.call': {
      if (isBlank(c.tool_id)) {
        add('tool_id', 'Choose a tool.');
        break;
      }
      const input = asObj(c.input);
      const preset = TOOL_REQUIRED_INPUT[String(c.tool_id)];
      for (const [key, message] of preset ?? []) {
        if (isBlank(input[key])) add(`input.${key}`, message);
      }
      if (c.tool_id === 'gmail_send_email' && !isBlank(input.to)) {
        const problem = recipientProblem(input.to);
        if (problem) add('input.to', problem);
      }
      if (!preset) {
        for (const key of requiredInputsFor(String(c.tool_id))) {
          if (isBlank(input[key])) add(`input.${key}`, `Enter a value for "${key}".`);
        }
      }
      break;
    }
    case 'router.llm': {
      if (isBlank(c.prompt)) add('prompt', 'Describe how the AI should choose a path.');
      const paths = out.filter((e) => edgeRoute(e as FlowEdge) === 'option');
      if (paths.length === 0) add('options', 'Connect at least one path from this step.');
      else {
        if (paths.some((e) => isBlank(e.label))) add('options', 'Give every path a label so the AI can pick it.');
        if (!paths.some((e) => e.target === c.default)) add('default', 'Choose the path to use when nothing matches.');
      }
      break;
    }
    case 'condition':
      if (isBlank(c.expression)) add('expression', "Enter the check, for example input['amount'] > 100.");
      missingBranches(node, out, c, add);
      break;
    case 'foreach':
      if (refProblem(c.items)) add('items', 'Choose the list to loop over.');
      if (typeof c.max_iterations !== 'number' || c.max_iterations < 0) add('max_iterations', 'Enter the maximum number of items to process.');
      if (c.on_item_error !== 'fail' && c.on_item_error !== 'skip') add('on_item_error', 'Choose what happens when an item fails.');
      if (refProblem(c.collect)) add('collect', 'Choose which result to collect from each item.');
      missingBranches(node, out, c, add);
      break;
    case 'human.approval':
      if (isBlank(c.message)) add('message', 'Write the message the approver will see.');
      if (c.approver_type !== 'role' && c.approver_type !== 'user') add('approver_type', 'Choose who can approve.');
      if (c.approver_type === 'role' && isBlank(c.approver_role)) add('approver_role', 'Choose the role that can approve.');
      if (c.approver_type === 'user' && isBlank(c.approver_users)) add('approver_users', 'Enter at least one approver.');
      if (typeof c.timeout_ms === 'number' && c.timeout_ms < 1) add('timeout_ms', 'The timeout must be at least 1 minute.');
      missingBranches(node, out, c, add);
      break;
    case 'transform': {
      const spec = getTransformOp(c.op as string | undefined);
      if (!spec) {
        add('op', 'Choose what to do with the data.');
        break;
      }
      const input = asObj(c.input);
      for (const p of spec.params) {
        if (!spec.optional?.includes(p) && isBlank(input[p])) add(`input.${p}`, `Enter a value for "${transformParamHelp(spec.name, p).label}".`);
      }
      break;
    }
    case 'state.get':
    case 'state.set':
    case 'state.delete':
      if (isBlank(c.key)) add('key', 'Enter the key.');
      if (kind === 'state.set' && isBlank(c.value)) add('value', 'Enter the value to save.');
      break;
    case 'doc.create':
      if (isBlank(c.doctype)) add('doctype', 'Enter the document type to create.');
      break;
    case 'code.run':
      if (isBlank(c.code)) add('code', 'Add the Python code to run.');
      else if (typeof c.code === 'string' && new TextEncoder().encode(c.code).length > MAX_CODE_BYTES) add('code', 'The code is too long. Keep it under 64 KB.');
      if (isBlank(c.profile)) add('profile', 'Choose how the code is allowed to run.');
      if (c.timeout_s !== undefined && (typeof c.timeout_s !== 'number' || !Number.isInteger(c.timeout_s) || c.timeout_s < 1)) {
        add('timeout_s', 'The time limit must be at least 1 second.');
      }
      if (Object.keys(asObj(c.inputs)).some((k) => k.trim() === '')) add('inputs', 'Give every input a name.');
      break;
    default:
      break;
  }
  return issues;
}

function missingBranches(
  node: NodeLike,
  out: EdgeLike[],
  config: Cfg,
  add: (field: string, message: string) => void
) {
  const t = asObj(node.data.actionConfig).type as string;
  for (const h of branchHandlesFor(t, config)) {
    if (h.optional) continue;
    if (!out.some((e) => edgeRoute(e as FlowEdge) === h.route)) add(`branch.${h.route}`, `Connect the "${h.label}" path to a next step.`);
  }
}

/**
 * `purpose: 'save'` lets a placeholder trigger (nothing chosen yet) through, since a draft with an unset
 * trigger is valid to store; run and publish need every step finished.
 */
export function validateFlow(nodes: NodeLike[], edges: EdgeLike[], purpose: 'save' | 'run' = 'run'): FlowIssue[] {
  const issues = nodes
    .flatMap((n) => validateNode(n, edges))
    .filter((i) => !(purpose === 'save' && i.kind === 'trigger.unset'));
  if (!nodes.some((n) => n.data.nodeType === 'trigger')) {
    issues.unshift({ nodeId: '', nodeLabel: 'Flow', kind: 'flow', field: 'trigger', message: 'Add a trigger so the flow knows when to start.' });
  }
  // A step nothing leads to can never run, and the server refuses to store it.
  const orphans = unreachableNodeIds(nodes as Array<Pick<FlowNode, 'id' | 'data'>>, edges);
  for (const n of nodes) {
    if (orphans.has(n.id)) {
      issues.push({
        nodeId: n.id,
        nodeLabel: n.data.label || nodeKind(n),
        kind: 'flow',
        field: 'connection',
        message: 'Nothing leads to this step. Connect it to the flow or delete it.',
      });
    }
  }
  return issues;
}

/** One readable sentence for a toast: "Can't save yet: Run agent: Choose an agent. (+2 more)". */
export function summarizeIssues(issues: FlowIssue[]): string {
  if (issues.length === 0) return '';
  const first = issues[0];
  const where = first.nodeId ? `${first.nodeLabel}: ` : '';
  const more = issues.length > 1 ? ` (and ${issues.length - 1} more to fix)` : '';
  return `${where}${first.message}${more}`;
}

/** Turn a raw save/run/publish error (schema text, Frappe traceback, HTML) into plain product copy. */
export function humanizeFlowError(err: unknown, fallback = 'Something went wrong. Try again.'): string {
  let text = err instanceof Error ? err.message : typeof err === 'string' ? err : '';
  for (let prev = ''; prev !== text; ) {
    prev = text;
    text = text.replace(/<[^>]*>/g, '');
  }
  text = text.trim();
  if (!text) return fallback;
  if (/UNREACHABLE_NODE|not reachable from entry/i.test(text)) return 'A step is not connected to the flow. Connect it or delete it, then save again.';
  const lower = text.toLowerCase();
  const required = /'([a-z_]+)' is a required property/i.exec(text);
  if (required) return `A required setting is missing (${required[1].replace(/_/g, ' ')}). Open the highlighted step and fill it in.`;
  if (/additional properties are not allowed|schema|jsonschema|validation error|is not valid under any/i.test(lower)) {
    return 'Some step settings are not valid. Open the steps marked as needing attention and check their fields.';
  }
  if (/timestamp|modified|has been modified|document has been modified/i.test(lower)) {
    return 'This flow was changed somewhere else. Reload the page and try again.';
  }
  if (/permission|not permitted|forbidden/i.test(lower)) return "You don't have permission to do that.";
  if (/network|failed to fetch|timeout|timed out/i.test(lower)) return 'Could not reach the server. Check your connection and try again.';
  const firstLine = text.split('\n').find((l) => l.trim()) ?? text;
  return firstLine.length > 200 ? `${firstLine.slice(0, 197)}...` : firstLine;
}
