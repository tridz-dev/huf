import { readFileSync } from 'node:fs';
import path from 'node:path';
import Ajv2020 from 'ajv/dist/2020';
import { describe, it, expect } from 'vitest';
import {
  ACTION_TO_BACKEND_TYPE,
  deserializeFlow,
  makeFlowEdge,
  mapBackendStatusToFrontend,
  serializeFlow,
} from '@/services/flowSerializer';
import { ACTION_CARD_CONTRACT, actionOptions } from '@/data/actions';
import type { BackendFlowGraph, BackendNode } from '@/services/flowApi';
import type {
  ActionConfig,
  EndConfig,
  Flow,
  FlowEdge,
  FlowEdgeRoute,
  FlowNode,
  TriggerConfig,
} from '@/types/flow.types';

// ─── Schema validator (huf/ai/graph/graph_ir.schema.json, $defs/FlowGraph) ───

const SCHEMA_PATH = path.resolve(__dirname, '../../../huf/ai/graph/graph_ir.schema.json');
const CONTRACT_DOC = path.resolve(__dirname, '../../../docs/flow/FIELD_CONTRACT.md');
const schema = JSON.parse(readFileSync(SCHEMA_PATH, 'utf8'));
const ajv = new Ajv2020({ strict: false, allErrors: true });
ajv.addSchema(schema);
const validateFlowGraph = ajv.getSchema(`${schema.$id}#/$defs/FlowGraph`)!;

function schemaErrors(graph: unknown): string[] {
  validateFlowGraph(graph);
  return (validateFlowGraph.errors ?? []).map((e) => `${e.instancePath} ${e.message}`);
}

// ─── Canvas builders ───────────────────────────────────────────────────

let y = 0;
function pos() {
  y += 100;
  return { x: 100, y };
}

function trigger(id: string, triggerConfig: TriggerConfig, configured = true): FlowNode {
  return {
    id,
    type: 'trigger',
    position: pos(),
    data: {
      label: `L ${id}`,
      nodeType: 'trigger',
      icon: 'Webhook',
      configured,
      ...(triggerConfig.type === undefined ? { description: 'Select a trigger' } : {}),
      triggerConfig,
    },
  };
}

function action(id: string, actionConfig: ActionConfig): FlowNode {
  return {
    id,
    type: 'action',
    position: pos(),
    data: { label: `L ${id}`, nodeType: 'action', icon: 'Play', configured: true, actionConfig },
  };
}

function end(id: string, endConfig: EndConfig): FlowNode {
  return {
    id,
    type: 'end',
    position: pos(),
    data: { label: 'End', nodeType: 'end', icon: 'CheckCircle2', configured: true, endConfig },
  };
}

function edge(
  source: string,
  target: string,
  route: FlowEdgeRoute = 'next',
  opts: { label?: string; index?: number; branchIndex?: number } = {}
): FlowEdge {
  return makeFlowEdge(source, target, route, opts);
}

function flowOf(nodes: FlowNode[], edges: FlowEdge[]): Flow {
  return {
    id: 'f1', name: 'F', status: 'draft', nodes, edges,
    createdAt: new Date(0), updatedAt: new Date(0), version: 1,
  };
}

const byId = <T extends { id: string }>(a: T, b: T) => a.id.localeCompare(b.id);

/** deserialize(serialize(x)) must equal x (edge order is not significant). */
function expectRoundTrip(flow: Flow) {
  const graph = serializeFlow(flow);
  const back = deserializeFlow(flow.id, flow.name, 'Draft', graph);
  expect(back.nodes).toEqual(flow.nodes);
  expect([...back.edges].sort(byId)).toEqual([...flow.edges].sort(byId));
  // and serializing again is a fixed point
  expect(serializeFlow(back)).toEqual(graph);
  return graph;
}

/**
 * The full canvas: every trigger (3) and every action card type (condition, router, human,
 * loop/foreach, agent, transform, tool.call presets for email/http/slack/sheets/file, state,
 * doc.create, validate) plus three End nodes.
 */
function fullCanvas(): Flow {
  const nodes: FlowNode[] = [
    trigger('t_webhook', { type: 'webhook', method: 'POST', secret: 'change-me-webhook-secret' }),
    trigger('t_schedule', { type: 'schedule', cron: '*/15 * * * *' }),
    trigger('t_doc', { type: 'doc-event', doctype: 'ToDo', event: 'after_insert' }),
    action('n_prep', { type: 'transform', op: 'trim', input: { text: { $from: 'input.message' } } }),
    action('n_agent', {
      type: 'agent-run', agent: 'support-triage', prompt: 'Classify: {message}',
      prompt_bindings: { message: { $from: 'n_prep' } },
    }),
    action('n_cond', { type: 'condition', expression: "input['amount'] > 100" }),
    action('n_router', { type: 'router', prompt: 'Urgent or routine?', default: 'n_loop' }),
    action('n_human', {
      type: 'human.approval', message: 'Approve?', approver_type: 'role',
      approver_role: 'System Manager', timeout_ms: 86400000,
    }),
    action('n_loop', {
      type: 'foreach', items: { $from: 'input.recipients' }, item_var: 'item', index_var: 'index',
      max_iterations: 100, on_item_error: 'skip', collect: { $from: 'n_email' },
    }),
    action('n_email', {
      type: 'tool-call', tool_id: 'gmail_send_email',
      input: {
        to: { $from: 'foreach.item' }, subject: 'Update',
        body: { $template: 'Hello {who}', vars: { who: { $from: 'foreach.item' } } },
      },
    }),
    action('n_http', {
      type: 'tool-call', tool_id: 'http_request', timeout_ms: 30000,
      input: { url: 'https://api.example.com/notify', method: 'POST', body: { ok: true } },
    }),
    action('n_slack', { type: 'tool-call', tool_id: 'slack_send_message', input: { channel: '#ops', text: 'done' } }),
    action('n_sheets', { type: 'tool-call', tool_id: 'gsheets_read', input: { spreadsheet_id: '1AbC', range: 'A1:D10' } }),
    action('n_file', { type: 'tool-call', tool_id: 'gdrive_list_files', input: { limit: 20 } }),
    action('n_state_set', { type: 'state-set', key: 'last_run', value: true, ttl_seconds: 3600 }),
    action('n_state_get', { type: 'state-get', key: 'last_run', default: false }),
    action('n_state_del', { type: 'state-delete', key: 'last_run' }),
    action('n_doc', { type: 'doc-create', doctype: 'ToDo', fields: { description: 'Flow done' } }),
    action('n_validate', {
      type: 'validate',
      assertions: [{ expression: "input['amount'] >= 0", code: 'NEG', message: 'amount must be non-negative' }],
    }),
    end('n_done', { value: { $from: 'n_doc' } }),
    end('n_done_small', { value: 'skipped' }),
    end('n_done_rejected', { value: 'rejected' }),
  ];
  const edges: FlowEdge[] = [
    edge('t_webhook', 'n_prep'),
    edge('t_schedule', 'n_prep'),
    edge('t_doc', 'n_prep'),
    edge('n_prep', 'n_agent'),
    edge('n_agent', 'n_cond'),
    edge('n_cond', 'n_router', 'true'),
    edge('n_cond', 'n_done_small', 'false'),
    edge('n_router', 'n_human', 'option', { label: 'urgent', index: 0 }),
    edge('n_router', 'n_loop', 'option', { label: 'routine', index: 1 }),
    edge('n_human', 'n_loop', 'approve'),
    edge('n_human', 'n_done_rejected', 'reject'),
    edge('n_human', 'n_done_rejected', 'timeout'),
    edge('n_loop', 'n_email', 'body', { index: 0 }),
    edge('n_loop', 'n_http', 'next'),
    edge('n_http', 'n_slack'),
    edge('n_slack', 'n_sheets'),
    edge('n_sheets', 'n_file'),
    edge('n_file', 'n_state_set'),
    edge('n_state_set', 'n_state_get'),
    edge('n_state_get', 'n_state_del'),
    edge('n_state_del', 'n_doc'),
    edge('n_doc', 'n_validate'),
    edge('n_validate', 'n_done'),
    edge('n_doc', 'n_done_small', 'error'),
  ];
  return flowOf(nodes, edges);
}

const nodeOf = (g: BackendFlowGraph, id: string) => g.nodes.find((n) => n.id === id)!;

// ─── Tests ─────────────────────────────────────────────────────────────

describe('flowSerializer: schema-valid output and lossless round trip', () => {
  it('serializes the full canvas to a graph-IR valid definition and round-trips it', () => {
    const flow = fullCanvas();
    const graph = expectRoundTrip(flow);
    expect(schemaErrors(graph)).toEqual([]);
    expect(graph.entry).toEqual(['t_webhook', 't_schedule', 't_doc']);
  });

  it('emits routing pointers derived from edges', () => {
    const g = serializeFlow(fullCanvas());
    expect(nodeOf(g, 'n_cond').config).toEqual({ expression: "input['amount'] > 100", on_true: 'n_router', on_false: 'n_done_small' });
    expect(nodeOf(g, 'n_cond')).not.toHaveProperty('next');
    expect(nodeOf(g, 'n_router').config).toEqual({
      prompt: 'Urgent or routine?',
      options: [{ label: 'urgent', node_id: 'n_human' }, { label: 'routine', node_id: 'n_loop' }],
      default: 'n_loop',
    });
    expect(nodeOf(g, 'n_human').config).toMatchObject({
      approve_next: 'n_loop', reject_next: 'n_done_rejected', timeout_next: 'n_done_rejected',
      approver_type: 'role', approver_role: 'System Manager',
    });
    expect(nodeOf(g, 'n_human')).not.toHaveProperty('next');
    expect(nodeOf(g, 'n_loop').config.body).toEqual(['n_email']);
    expect(nodeOf(g, 'n_loop').next).toBe('n_http');
    expect(nodeOf(g, 'n_email')).not.toHaveProperty('next');
    expect(nodeOf(g, 'n_doc').on_error).toBe('n_done_small');
  });

  it('serializes End as an output node with value and no next key', () => {
    const g = serializeFlow(fullCanvas());
    const out = nodeOf(g, 'n_done');
    expect(out.type).toBe('output');
    expect(out.config).toEqual({ value: { $from: 'n_doc' } });
    expect(Object.keys(out)).not.toContain('next');
  });

  it('never writes next on an output node even when an edge leaves End', () => {
    const flow = fullCanvas();
    flow.edges.push(edge('n_done', 'n_prep'));
    const out = nodeOf(serializeFlow(flow), 'n_done');
    expect(Object.keys(out)).not.toContain('next');
  });

  it('serializes an End with no value as value:null (schema requires value)', () => {
    const g = serializeFlow(flowOf([trigger('t', { type: 'schedule', cron: '* * * * *' }), end('e', {})], [edge('t', 'e')]));
    expect(nodeOf(g, 'e').config).toEqual({ value: null });
    expect(schemaErrors(g)).toEqual([]);
  });

  it('round-trips parallel (branch chains + join next) and router.decision', () => {
    const flow = flowOf(
      [
        trigger('t', { type: 'schedule', cron: '0 * * * *' }),
        action('p', { type: 'parallel', join: 'all', max_parallel_calls: 2 }),
        action('a1', { type: 'tool-call', tool_id: 'slack_send_message', input: { channel: '#a', text: 'x' } }),
        action('a2', { type: 'state-delete', key: 'k' }),
        action('b1', { type: 'state-get', key: 'k' }),
        action('d', { type: 'router-decision', policy: 'by_amount', default: 'e1' }),
        end('e1', { value: 1 }),
        end('e2', { value: 2 }),
      ],
      [
        edge('t', 'p'),
        edge('p', 'a1', 'branch', { branchIndex: 0, index: 0 }),
        edge('a1', 'a2'),
        edge('p', 'b1', 'branch', { branchIndex: 1, index: 1 }),
        edge('p', 'd', 'next'),
        edge('d', 'e1', 'option', { label: 'low', index: 0 }),
        edge('d', 'e2', 'option', { label: 'high', index: 1 }),
      ]
    );
    const g = expectRoundTrip(flow);
    expect(nodeOf(g, 'p').config).toEqual({ join: 'all', max_parallel_calls: 2, branches: [['a1', 'a2'], ['b1']] });
    expect(nodeOf(g, 'd').type).toBe('router.decision');
    expect(schemaErrors(g)).toEqual([]);
  });

  it('round-trips a router whose default is not an option target (default edge)', () => {
    const flow = flowOf(
      [
        trigger('t', { type: 'schedule', cron: '0 * * * *' }),
        action('r', { type: 'router', prompt: 'p', default: 'e0' }),
        end('e0', { value: 0 }),
        end('e1', { value: 1 }),
      ],
      [edge('t', 'r'), edge('r', 'e1', 'option', { label: 'one', index: 0 }), edge('r', 'e0', 'default')]
    );
    const g = expectRoundTrip(flow);
    expect(nodeOf(g, 'r').config.default).toBe('e0');
    expect(schemaErrors(g)).toEqual([]);
  });

  it('round-trips the trigger.unset placeholder and keeps it schema-valid', () => {
    const flow = flowOf([trigger('empty_trigger', { type: undefined }, false)], []);
    const g = expectRoundTrip(flow);
    expect(nodeOf(g, 'empty_trigger').type).toBe('trigger.unset');
    expect(nodeOf(g, 'empty_trigger').config).toEqual({});
    expect(schemaErrors(g)).toEqual([]);
  });

  it('preserves state/doc.create/validate/foreach/parallel as their real types', () => {
    const g = serializeFlow(fullCanvas());
    const types = Object.fromEntries(g.nodes.map((n) => [n.id, n.type]));
    expect(types).toMatchObject({
      n_state_set: 'state.set', n_state_get: 'state.get', n_state_del: 'state.delete',
      n_doc: 'doc.create', n_validate: 'validate', n_loop: 'foreach', n_email: 'tool.call',
    });
  });

  it('derives the permission envelope from the tools and doc.create nodes the graph uses', () => {
    const g = serializeFlow(fullCanvas());
    expect(g.contract.permission_envelope.http).toEqual(['http_request']);
    expect(g.contract.permission_envelope.code).toBe('none');
    expect(g.contract.permission_envelope.write).toEqual([{ doctype: 'ToDo' }]);
  });
});

describe('flowSerializer: pointers are recomputed from edges on every save', () => {
  it('ignores routing keys smuggled into canvas config (no stale pointers)', () => {
    const flow = fullCanvas();
    const cond = flow.nodes.find((n) => n.id === 'n_cond')!;
    cond.data.actionConfig = { ...(cond.data.actionConfig as object), on_true: 'n_done', on_false: 'n_done' } as unknown as ActionConfig;
    const g = serializeFlow(flow);
    expect(nodeOf(g, 'n_cond').config).toMatchObject({ on_true: 'n_router', on_false: 'n_done_small' });
  });

  it('follows edge edits: swapping the True/False targets swaps on_true/on_false', () => {
    const flow = fullCanvas();
    flow.edges = flow.edges.filter((e) => e.source !== 'n_cond');
    flow.edges.push(edge('n_cond', 'n_done_small', 'true'), edge('n_cond', 'n_router', 'false'));
    const cfg = nodeOf(serializeFlow(flow), 'n_cond').config;
    expect(cfg).toMatchObject({ on_true: 'n_done_small', on_false: 'n_router' });
  });

  it('omits a condition branch whose edge was deleted instead of keeping the old target', () => {
    const flow = fullCanvas();
    flow.edges = flow.edges.filter((e) => !(e.source === 'n_cond' && e.target === 'n_done_small'));
    const cfg = nodeOf(serializeFlow(flow), 'n_cond').config;
    expect(cfg).not.toHaveProperty('on_false');
    expect(cfg.on_true).toBe('n_router');
  });

  it('drops a deleted router option and re-points a stale default to the first remaining option', () => {
    const flow = fullCanvas();
    flow.edges = flow.edges.filter((e) => !(e.source === 'n_router' && e.target === 'n_loop'));
    const cfg = nodeOf(serializeFlow(flow), 'n_router').config as { options: unknown[]; default: string };
    expect(cfg.options).toEqual([{ label: 'urgent', node_id: 'n_human' }]);
    expect(cfg.default).toBe('n_human');
  });

  it('accepts handle-only edges (sourceHandle) as routes', () => {
    const flow = fullCanvas();
    flow.edges = flow.edges.map((e) => {
      if (e.source !== 'n_cond') return e;
      const rest = { ...e };
      delete rest.data;
      return rest;
    });
    const cfg = nodeOf(serializeFlow(flow), 'n_cond').config;
    expect(cfg).toMatchObject({ on_true: 'n_router', on_false: 'n_done_small' });
  });

  it('drops edges that point at missing nodes', () => {
    const flow = fullCanvas();
    flow.edges.push(edge('n_prep', 'ghost'));
    const g = serializeFlow(flow);
    expect(schemaErrors(g)).toEqual([]);
    expect(nodeOf(g, 'n_prep').next).toBe('n_agent');
  });

  it('follows body chain edits: extending the chain extends body', () => {
    const flow = fullCanvas();
    flow.nodes.push(action('n_extra', { type: 'state-delete', key: 'x' }));
    flow.edges.push(edge('n_email', 'n_extra'));
    expect(nodeOf(serializeFlow(flow), 'n_loop').config.body).toEqual(['n_email', 'n_extra']);
  });
});

describe('flowSerializer: contract example (graph -> canvas -> graph)', () => {
  const doc = readFileSync(CONTRACT_DOC, 'utf8');
  const canonical = JSON.parse(/```json\n([\s\S]*?)\n```/.exec(doc)![1]) as BackendFlowGraph;
  const strip = (nodes: BackendNode[]) =>
    nodes.map(({ _position, _label, _icon, ...n }) => { void _position; void _label; void _icon; return n; });

  it('the canonical flow in FIELD_CONTRACT.md is schema-valid (sanity of the validator)', () => {
    expect(schemaErrors(canonical)).toEqual([]);
  });

  it('survives deserialize -> serialize with identical nodes and a schema-valid result', () => {
    const flow = deserializeFlow('f', 'F', 'Draft', canonical);
    const out = serializeFlow(flow);
    expect(strip(out.nodes)).toEqual(strip(canonical.nodes));
    expect(out.entry).toEqual(canonical.entry);
    expect(out.contract.permission_envelope).toEqual(canonical.contract.permission_envelope);
    expect(schemaErrors(out)).toEqual([]);
  });
});

describe('flowSerializer: negative tests', () => {
  const good = () => structuredClone(serializeFlow(fullCanvas())) as BackendFlowGraph & Record<string, unknown>;

  it('the validator accepts the untouched serializer output', () => {
    expect(schemaErrors(good())).toEqual([]);
  });

  it.each<[string, (g: BackendFlowGraph & Record<string, unknown>) => void]>([
    ['a top-level edges array', (g) => { g.edges = []; }],
    ['numeric schema_version', (g) => { (g as Record<string, unknown>).schema_version = 1; }],
    ['webhook PUT method', (g) => { nodeOf(g, 't_webhook').config.method = 'PUT'; }],
    ['webhook secret too short', (g) => { nodeOf(g, 't_webhook').config.secret = 'short'; }],
    ['legacy webhook key', (g) => { nodeOf(g, 't_webhook').config.apiKey = 'k'; }],
    ['doc-event legacy event', (g) => { nodeOf(g, 't_doc').config.event = 'save'; }],
    ['legacy tool_name key', (g) => { nodeOf(g, 'n_slack').config.tool_name = 'x'; }],
    ['next on output', (g) => { (nodeOf(g, 'n_done') as BackendNode).next = null; }],
    ['next on condition', (g) => { nodeOf(g, 'n_cond').next = 'n_done'; }],
    ['condition without on_false', (g) => { delete nodeOf(g, 'n_cond').config.on_false; }],
    ['router without default', (g) => { delete nodeOf(g, 'n_router').config.default; }],
    ['id with dash', (g) => { nodeOf(g, 'n_prep').id = 'n-prep'; }],
    ['bad fingerprint', (g) => { g.fingerprint = 'nope'; }],
  ])('rejects %s', (_name, mutate) => {
    const g = good();
    mutate(g);
    expect(schemaErrors(g).length).toBeGreaterThan(0);
  });

  it('serializer output never contains legacy keys', () => {
    const text = JSON.stringify(serializeFlow(fullCanvas()).nodes.map((n) => n.config));
    for (const legacy of ['tool_name', 'save_result_to_context', 'agent_name', 'prompt_template', 'true_node', 'loop_node', 'iterate_over', 'apiKey', 'mcp_server', 'gateway']) {
      expect(text).not.toContain(`"${legacy}"`);
    }
  });

  it('never rewrites an unknown backend type as tool.call', () => {
    const graph: BackendFlowGraph = {
      ...serializeFlow(flowOf([], [])),
      entry: 'x',
      nodes: [{ id: 'x', type: 'future.node' as never, config: { a: 1 }, next: 'y' }, { id: 'y', type: 'output', config: { value: 1 } }],
    };
    const flow = deserializeFlow('f', 'F', 'Draft', graph);
    expect(flow.nodes[0].data.actionConfig).toMatchObject({ type: 'unknown', backend_type: 'future.node' });
    expect(nodeOf(serializeFlow(flow), 'x')).toMatchObject({ type: 'future.node', config: { a: 1 }, next: 'y' });
  });
});

describe('flowSerializer: sidecar fields and helpers', () => {
  it('preserves _position, _label and _icon as node-level extras (config stays clean)', () => {
    const g = serializeFlow(fullCanvas());
    const n = nodeOf(g, 'n_prep');
    expect(n._position).toBeDefined();
    expect(n._label).toBe('L n_prep');
    expect(n._icon).toBe('Play');
    expect(Object.keys(n.config).filter((k) => k.startsWith('_'))).toEqual([]);
  });

  it('auto-layouts nodes vertically when _position is absent', () => {
    const graph = serializeFlow(fullCanvas());
    graph.nodes.forEach((n) => { delete n._position; });
    const flow = deserializeFlow('f', 'F', 'Draft', graph);
    expect(flow.nodes[2].position).toEqual({ x: 250, y: 300 });
  });

  it('handles an empty flow and a flow with no trigger', () => {
    expect(serializeFlow(flowOf([], [])).nodes).toEqual([]);
    const g = serializeFlow(flowOf([action('a', { type: 'state-delete', key: 'k' })], []));
    expect(g.entry).toBe('a');
  });

  it('computes configured from real config', () => {
    const graph = serializeFlow(flowOf([action('a', { type: 'state-get' }), action('b', { type: 'foreach' })], []));
    const flow = deserializeFlow('f', 'F', 'Draft', graph);
    expect(flow.nodes.map((n) => n.data.configured)).toEqual([false, false]);
  });

  it('maps backend status', () => {
    expect(mapBackendStatusToFrontend('Active')).toBe('active');
    expect(mapBackendStatusToFrontend('Archived')).toBe('paused');
    expect(mapBackendStatusToFrontend('nope')).toBe('draft');
  });
});

describe('action cards (src/data/actions.ts)', () => {
  it('has a contract mapping for every card and no Execute Code card', () => {
    const ids = actionOptions.map((a) => a.id);
    expect(ids).not.toContain('code');
    expect(ids.sort()).toEqual(Object.keys(ACTION_CARD_CONTRACT).sort());
  });

  it('maps each card to the node type its config discriminator serializes to', () => {
    for (const c of Object.values(ACTION_CARD_CONTRACT)) {
      expect(ACTION_TO_BACKEND_TYPE[c.configType]).toBe(c.backendType);
    }
  });

  it('maps the tool presets to the contract tool ids', () => {
    expect(ACTION_CARD_CONTRACT.email.toolId).toBe('gmail_send_email');
    expect(ACTION_CARD_CONTRACT['http-request'].toolId).toBe('http_request');
    expect(ACTION_CARD_CONTRACT.slack.toolIds).toEqual(['slack_send_message', 'slack_send_thread_reply']);
    expect(ACTION_CARD_CONTRACT.sheets.toolIds).toEqual(['gsheets_read', 'gsheets_update', 'gsheets_create']);
    expect(ACTION_CARD_CONTRACT.file.toolIds).toEqual(['gdrive_list_files', 'gdrive_search_files', 'gdrive_get_file']);
  });
});
