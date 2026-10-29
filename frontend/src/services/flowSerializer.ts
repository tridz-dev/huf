/**
 * Flow Serializer — Bidirectional conversion between React Flow format
 * and the backend's shared graph-IR definition_json (Flow profile).
 *
 * Every save/load must go through serializeFlow / deserializeFlow.
 *
 * v0.4 — Schema-exact: field names follow docs/flow/FIELD_CONTRACT.md; routing
 *   pointers are recomputed from edges on every save (never stored in canvas config).
 * v0.3 — Migrated to the shared graph-IR shape (huf/ai/graph/graph_ir.schema.json
 *   `$defs/FlowGraph`): nodes carry their own `next`/`on_error` pointers, there is no
 *   top-level `edges` array, and `schema_version` is the literal string "1.0.0". A
 *   React Flow edge is still how the canvas represents a connection visually -- this
 *   module folds it into the source node's `next`/`on_error`/self-routing config at
 *   serialize time, and reconstructs it from those pointers at deserialize time. See
 *   huf/huf/doctype/flow_definition/flow_definition.py's `_validate_definition_json`
 *   for the server-side gate this shape now has to satisfy, and
 *   the DeterministicAgent workspace track for the shape itself.
 */

import type {
    ActionConfig, ActionType, Flow, FlowEdge, FlowEdgeRoute, FlowNode, FlowNodeData, FlowStatus, TriggerConfig,
} from '@/types/flow.types';
import type { BackendFlowGraph, BackendNode, BackendNodeType } from './flowApi';
import { defaultContract, deriveContract, placeholderFingerprint } from './flow/flowContract';

export { defaultContract };

// ─── Shared tables ───────────────────────────────────────────────────

/** Canvas action discriminator -> graph-IR node type. */
export const ACTION_TO_BACKEND_TYPE: Record<ActionType, BackendNodeType> = {
    'agent-run': 'agent.run',
    'tool-call': 'tool.call',
    'router': 'router.llm',
    'router-decision': 'router.decision',
    'human.approval': 'human.approval',
    'condition': 'condition',
    'foreach': 'foreach',
    'validate': 'validate',
    'transform': 'transform',
    'state-get': 'state.get',
    'state-set': 'state.set',
    'state-delete': 'state.delete',
    'doc-create': 'doc.create',
    'code-run': 'code.run',
};

const BACKEND_TO_ACTION_TYPE: Record<string, ActionType> = Object.fromEntries(
    Object.entries(ACTION_TO_BACKEND_TYPE).map(([a, b]) => [b, a as ActionType])
);

/** Config keys that are routing pointers: derived from edges, never held in canvas config. */
const ROUTING_KEYS: Partial<Record<BackendNodeType, string[]>> = {
    'condition': ['on_true', 'on_false'],
    'router.llm': ['options'],
    'router.decision': ['options'],
    'human.approval': ['approve_next', 'reject_next', 'timeout_next'],
    'foreach': ['body'],
};

/** Node types with no `next` key at all. */
const NO_NEXT_TYPES = new Set<string>(['condition', 'router.llm', 'router.decision', 'human.approval', 'output']);

/** Valid values of a handle id / edge route other than 'next'. */
export const FLOW_EDGE_ROUTES: readonly FlowEdgeRoute[] = [
    'next', 'error', 'true', 'false', 'option', 'default', 'approve', 'reject', 'timeout', 'body',
];

const ROUTE_LABELS: Partial<Record<FlowEdgeRoute, string>> = {
    error: 'On error', true: 'True', false: 'False', default: 'Default',
    approve: 'Approved', reject: 'Rejected', timeout: 'Timed out', body: 'Each item',
};

/** Route of a canvas edge: `data.route`, else the source handle id, else 'next'. */
export function edgeRoute(edge: FlowEdge): FlowEdgeRoute {
    const fromData = (edge.data as { route?: FlowEdgeRoute } | undefined)?.route;
    if (fromData) return fromData;
    const handle = edge.sourceHandle as FlowEdgeRoute | null | undefined;
    if (handle && FLOW_EDGE_ROUTES.includes(handle)) return handle;
    return 'next';
}

/** Deterministic edge id. `index` disambiguates repeated routes (options, body heads, branches). */
export function makeFlowEdgeId(source: string, route: FlowEdgeRoute, target: string, index?: number): string {
    return `${source}:${route}${index === undefined ? '' : `#${index}`}->${target}`;
}

export interface MakeFlowEdgeOptions {
    /** router option label (route 'option'). */
    label?: string;
    /** position among same-route edges of the source (option/body). */
    index?: number;
}

/** Build the canonical canvas edge for a route. Used by deserialize; WP-D should use it for new connections. */
export function makeFlowEdge(source: string, target: string, route: FlowEdgeRoute, opts: MakeFlowEdgeOptions = {}): FlowEdge {
    const label = route === 'option' ? opts.label ?? target
        : ROUTE_LABELS[route];
    const data: { route: FlowEdgeRoute } = { route };
    const edge: FlowEdge = {
        id: makeFlowEdgeId(source, route, target, route === 'option' || route === 'body' ? opts.index ?? 0 : undefined),
        source,
        target,
        type: 'default',
        data,
    };
    if (route !== 'next') edge.sourceHandle = route;
    if (label !== undefined) edge.label = label;
    return edge;
}

// ─── Frontend → Backend ──────────────────────────────────────────────

/**
 * Convert a frontend Flow object into the backend graph JSON. Output is schema-valid
 * for any canvas state in which every required field has been filled in; required
 * routing fields whose edge is missing are omitted (never defaulted to a stale target).
 */
export function serializeFlow(flow: Flow): BackendFlowGraph {
    const ids = new Set(flow.nodes.map((n) => n.id));

    // Outgoing edges per source; dangling edges (missing source/target) are dropped.
    const outgoingBySource = new Map<string, FlowEdge[]>();
    for (const edge of flow.edges) {
        if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
        const list = outgoingBySource.get(edge.source) ?? [];
        list.push(edge);
        outgoingBySource.set(edge.source, list);
    }

    // `next` target of each node: body/branch chains are followed through it.
    const nextOf = new Map<string, string>();
    for (const [source, edges] of outgoingBySource) {
        const e = edges.find((x) => edgeRoute(x) === 'next');
        if (e) nextOf.set(source, e.target);
    }

    const nodes = flow.nodes.map((node) => serializeNode(node, outgoingBySource.get(node.id) ?? [], nextOf));
    const triggerIds = flow.nodes.filter((n) => n.data?.nodeType === 'trigger').map((n) => n.id);

    return {
        schema_version: '1.0.0',
        profile: 'flow',
        fingerprint: placeholderFingerprint(JSON.stringify(nodes.map((n) => [n.id, n.type, n.config, n.next, n.on_error]))),
        entry: triggerIds.length ? triggerIds : flow.nodes[0]?.id ?? '',
        nodes,
        contract: deriveContract(nodes),
    };
}

/** Follow `next` from a chain head collecting ids (cycle-safe). */
function walkChain(head: string, nextOf: Map<string, string>, seen: Set<string>): string[] {
    const out: string[] = [];
    let cur: string | undefined = head;
    while (cur && !seen.has(cur)) {
        seen.add(cur);
        out.push(cur);
        cur = nextOf.get(cur);
    }
    return out;
}

function serializeNode(node: FlowNode, outgoing: FlowEdge[], nextOf: Map<string, string>): BackendNode {
    const type = mapFrontendNodeTypeToBackend(node);
    const config = extractNodeConfig(node, type);
    const byRoute = (route: FlowEdgeRoute) => outgoing.filter((e) => edgeRoute(e) === route);
    const first = (route: FlowEdgeRoute) => byRoute(route)[0]?.target;
    const setIf = (key: string, value: unknown) => { if (value !== undefined) config[key] = value; };

    switch (type) {
        case 'condition':
            setIf('on_true', first('true'));
            setIf('on_false', first('false'));
            break;
        case 'router.llm':
        case 'router.decision': {
            const options = byRoute('option').map((e) => ({
                label: typeof e.label === 'string' && e.label !== '' ? e.label : e.target,
                node_id: e.target,
            }));
            config.options = options;
            // Recomputed from current edges: a default that is no longer a routed target is dropped.
            const routed = new Set([...options.map((o) => o.node_id), ...byRoute('default').map((e) => e.target)]);
            const wanted = first('default') ?? (typeof config.default === 'string' ? config.default : undefined);
            delete config.default;
            setIf('default', wanted && routed.has(wanted) ? wanted : options[0]?.node_id);
            break;
        }
        case 'human.approval':
            setIf('approve_next', first('approve'));
            setIf('reject_next', first('reject'));
            setIf('timeout_next', first('timeout'));
            break;
        case 'foreach': {
            const seen = new Set<string>();
            const body = byRoute('body').flatMap((e) => walkChain(e.target, nextOf, seen));
            if (body.length) config.body = body;
            break;
        }
        case 'output':
            if (config.value === undefined) config.value = null;
            break;
        case 'tool.call':
            if (config.input === undefined) config.input = {};
            break;
        case 'code.run':
            if (config.inputs === undefined || config.inputs === null || typeof config.inputs !== 'object') config.inputs = {};
            if (typeof config.timeout_s !== 'number') delete config.timeout_s;
            break;
        default:
            break;
    }

    const out: BackendNode = { id: node.id, type, config };
    if (!NO_NEXT_TYPES.has(type)) {
        const next = first('next');
        if (next !== undefined) out.next = next;
    }
    const onError = first('error');
    if (onError !== undefined) out.on_error = onError;

    out._position = node.position;
    if (node.data?.label !== undefined) out._label = node.data.label;
    if (node.data?.icon !== undefined) out._icon = node.data.icon;
    if (node.data?.disabled) out._disabled = true;
    if (node.data?.notes) out._notes = node.data.notes;
    if (node.data?.sample !== undefined) out._sample = node.data.sample;
    return out;
}

function mapFrontendNodeTypeToBackend(node: FlowNode): BackendNodeType {
    const nodeType = node.data?.nodeType;
    if (nodeType === 'end') return 'output';

    if (nodeType === 'trigger') {
        switch (node.data?.triggerConfig?.type) {
            case 'schedule': return 'trigger.schedule';
            case 'doc-event': return 'trigger.doc-event';
            case 'webhook': return 'trigger.webhook';
            // No trigger chosen yet (fresh flow): never invent a webhook.
            default: return 'trigger.unset';
        }
    }

    const cfg = node.data?.actionConfig;
    if (cfg?.type === 'unknown') return cfg.backend_type as BackendNodeType;
    if (cfg?.type && cfg.type in ACTION_TO_BACKEND_TYPE) return ACTION_TO_BACKEND_TYPE[cfg.type as ActionType];
    return 'tool.call'; // unconfigured action placeholder
}

/** Drop `type` (and `backend_type`) discriminators and undefined values. */
function plainConfig(cfg: { type?: string } & Record<string, unknown>): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(cfg)) {
        if (k === 'type' || v === undefined) continue;
        if (cfg.type === 'unknown' && k === 'backend_type') continue;
        out[k] = v;
    }
    return out;
}

function extractNodeConfig(node: FlowNode, backendType: BackendNodeType): Record<string, unknown> {
    const data = node.data;
    let config: Record<string, unknown> = {};

    if (backendType === 'output') {
        const value = data?.endConfig?.value;
        return value === undefined ? {} : { value };
    }
    if (backendType === 'trigger.unset') return {};

    if (backendType.startsWith('trigger.')) {
        config = plainConfig((data?.triggerConfig ?? {}) as Record<string, unknown>);
        const allowed = backendType === 'trigger.webhook' ? ['method', 'secret']
            : backendType === 'trigger.schedule' ? ['cron', 'time_zone'] : ['doctype', 'event'];
        return Object.fromEntries(Object.entries(config).filter(([k]) => allowed.includes(k)));
    }

    if (data?.actionConfig?.type) {
        config = plainConfig(data.actionConfig as Record<string, unknown>);
        // Routing pointers are never read from canvas config; they are recomputed from edges.
        for (const key of ROUTING_KEYS[backendType] ?? []) delete config[key];
    }
    return config;
}

// ─── Backend → Frontend ──────────────────────────────────────────────

/**
 * Convert a backend graph JSON into a frontend Flow object. Exact inverse of serializeFlow
 * for every canvas state serializeFlow can emit (positions fall back to a vertical layout).
 */
export function deserializeFlow(
    flowId: string,
    flowName: string,
    status: string,
    graph: BackendFlowGraph
): Flow {
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    return {
        id: flowId,
        name: flowName,
        status: mapBackendStatusToFrontend(status),
        nodes: graph.nodes.map((node, index) => deserializeNode(node, index)),
        edges: graph.nodes.flatMap((n) => deserializeEdgesForNode(n, byId)),
        createdAt: new Date(),
        updatedAt: new Date(),
        // Version lives on the Flow Definition doctype record, not in the graph.
        version: 1,
    };
}

function deserializeNode(node: BackendNode, index: number): FlowNode {
    return {
        id: node.id,
        type: mapBackendNodeTypeToFrontend(node.type),
        position: node._position || { x: 250, y: index * 150 },
        data: buildNodeData(node),
    };
}

function mapBackendNodeTypeToFrontend(backendType: string): string {
    if (backendType === 'output') return 'end';
    if (backendType.startsWith('trigger.')) return 'trigger';
    return 'action';
}

/**
 * Config keys that must be non-blank for a node to count as configured.
 * Mirrors the required string fields in graph_ir.schema.json.
 */
const REQUIRED_CONFIG_KEYS: Partial<Record<string, string[]>> = {
    'trigger.webhook': ['method', 'secret'],
    'trigger.schedule': ['cron'],
    'trigger.doc-event': ['doctype', 'event'],
    'agent.run': ['agent', 'prompt'],
    'tool.call': ['tool_id'],
    'router.llm': ['prompt'],
    'router.decision': ['policy'],
    'human.approval': ['message'],
    'condition': ['expression'],
    'foreach': ['items'],
    'validate': ['assertions'],
    'state.get': ['key'],
    'state.set': ['key'],
    'state.delete': ['key'],
    'doc.create': ['doctype'],
    'code.run': ['code', 'profile'],
    'transform': ['op'],
};

/** Computed from the real stored config, so the "unconfigured" warning survives reload. */
export function isBackendNodeConfigured(node: BackendNode): boolean {
    if (node.type === 'trigger.unset') return false;
    const config = (node.config ?? {}) as Record<string, unknown>;
    return (REQUIRED_CONFIG_KEYS[node.type] ?? []).every((key) => {
        if (key === 'secret' && config.secret_hidden === true) return true; // set, but hidden from a viewer
        const v = config[key];
        return v != null && !(typeof v === 'string' && v.trim() === '');
    });
}

function buildNodeData(node: BackendNode): FlowNodeData {
    const frontendType = mapBackendNodeTypeToFrontend(node.type);

    const base: FlowNodeData = {
        label: node._label || getDefaultLabel(node.type),
        nodeType: frontendType as FlowNodeData['nodeType'],
        icon: node._icon || getDefaultIcon(node.type),
        configured: isBackendNodeConfigured(node),
        ...(node._disabled === true ? { disabled: true } : {}),
        ...(typeof node._notes === 'string' && node._notes ? { notes: node._notes } : {}),
        ...(node._sample && typeof node._sample === 'object' ? { sample: node._sample } : {}),
    };

    if (node.type === 'trigger.unset') {
        base.description = 'Select a trigger';
        base.triggerConfig = { type: undefined };
    } else if (frontendType === 'trigger') {
        const type = node.type === 'trigger.schedule' ? 'schedule'
            : node.type === 'trigger.doc-event' ? 'doc-event' : 'webhook';
        base.triggerConfig = { type, ...node.config } as TriggerConfig;
    } else if (frontendType === 'end') {
        base.endConfig = { ...(node.config.value !== undefined ? { value: node.config.value } : {}) };
    } else {
        const config: Record<string, unknown> = { ...node.config };
        for (const key of ROUTING_KEYS[node.type] ?? []) delete config[key];
        const actionType = BACKEND_TO_ACTION_TYPE[node.type];
        base.actionConfig = (actionType
            ? { type: actionType, ...config }
            // Never coerce an unrecognised type into a tool call (it would be silently rewritten on save).
            : { type: 'unknown', backend_type: node.type, ...config }) as ActionConfig;
    }

    return base;
}

function getDefaultLabel(backendType: string): string {
    const labels: Record<string, string> = {
        'trigger.webhook': 'Webhook trigger',
        'trigger.schedule': 'Schedule trigger',
        'trigger.doc-event': 'Document event trigger',
        'trigger.unset': 'Select trigger',
        'agent.run': 'Run agent',
        'tool.call': 'Call tool',
        'router.llm': 'LLM router',
        'router.decision': 'Decision router',
        'human.approval': 'Human approval',
        'condition': 'Condition (IF)',
        'transform': 'Transform data',
        'foreach': 'Loop',
        'validate': 'Validate',
        'state.get': 'Get state',
        'state.set': 'Set state',
        'state.delete': 'Delete state',
        'doc.create': 'Create document',
        'code.run': 'Execute code',
        'output': 'End',
    };
    return labels[backendType] || backendType;
}

function getDefaultIcon(backendType: string): string {
    const icons: Record<string, string> = {
        'trigger.webhook': 'Webhook',
        'trigger.schedule': 'Clock',
        'trigger.doc-event': 'Database',
        'trigger.unset': 'CircleDashed',
        'agent.run': 'SquareAsterisk',
        'tool.call': 'Play',
        'router.llm': 'GitBranch',
        'router.decision': 'GitBranch',
        'human.approval': 'UserCheck',
        'condition': 'GitBranch',
        'transform': 'Repeat',
        'foreach': 'RotateCw',
        'validate': 'ShieldCheck',
        'state.get': 'Database',
        'state.set': 'Save',
        'state.delete': 'Trash2',
        'doc.create': 'FilePlus',
        'code.run': 'Terminal',
        'output': 'CheckCircle2',
    };
    return icons[backendType] || 'Play';
}

export function mapBackendStatusToFrontend(status: string): FlowStatus {
    const map: Record<string, FlowStatus> = {
        'Draft': 'draft',
        'Active': 'active',
        'Archived': 'paused',
    };
    return map[status] || 'draft';
}

/** Reconstruct this node's outgoing React Flow edges from its own next/on_error/
 * routing config -- the inverse of serializeNode's folding. */
function deserializeEdgesForNode(node: BackendNode, byId: Map<string, BackendNode>): FlowEdge[] {
    const edges: FlowEdge[] = [];
    const cfg = (node.config ?? {}) as Record<string, unknown>;
    const push = (to: unknown, route: FlowEdgeRoute, opts: MakeFlowEdgeOptions = {}) => {
        if (typeof to === 'string' && to) edges.push(makeFlowEdge(node.id, to, route, opts));
    };
    /** Heads of the chains in `ids`: an id is a head unless its predecessor's `next` is that id. */
    const heads = (ids: string[]) => ids.filter((id, i) => i === 0 || byId.get(ids[i - 1])?.next !== id);

    switch (node.type) {
        case 'condition':
            push(cfg.on_true, 'true');
            push(cfg.on_false, 'false');
            break;
        case 'router.llm':
        case 'router.decision': {
            const options = (cfg.options as Array<{ label: string; node_id: string }> | undefined) ?? [];
            options.forEach((o, index) => push(o.node_id, 'option', { label: o.label, index }));
            if (typeof cfg.default === 'string' && !options.some((o) => o.node_id === cfg.default)) push(cfg.default, 'default');
            break;
        }
        case 'human.approval':
            push(cfg.approve_next, 'approve');
            push(cfg.reject_next, 'reject');
            push(cfg.timeout_next, 'timeout');
            break;
        case 'foreach':
            heads((cfg.body as string[] | undefined) ?? []).forEach((id, index) => push(id, 'body', { index }));
            push(node.next, 'next');
            break;
        default:
            push(node.next, 'next');
    }

    push(node.on_error, 'error');
    return edges;
}
