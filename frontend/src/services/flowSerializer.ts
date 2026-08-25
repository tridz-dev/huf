/**
 * Flow Serializer — Bidirectional conversion between React Flow format
 * and the backend's shared graph-IR definition_json (Flow profile).
 *
 * Every save/load must go through serializeFlow / deserializeFlow.
 *
 * v0.3 — Migrated to the shared graph-IR shape (huf/ai/graph/graph_ir.schema.json
 *   `$defs/FlowGraph`): nodes carry their own `next`/`on_error` pointers, there is no
 *   top-level `edges` array, and `schema_version` is the literal string "1.0.0". A
 *   React Flow edge is still how the canvas represents a connection visually -- this
 *   module folds it into the source node's `next`/`on_error`/self-routing config at
 *   serialize time, and reconstructs it from those pointers at deserialize time. See
 *   huf/huf/doctype/flow_definition/flow_definition.py's `_validate_definition_json`
 *   for the server-side gate this shape now has to satisfy, and
 *   Tracks/safwan-erooth.DeterministicAgent/spec/graph-ir.md for the shape itself.
 */

import type { Flow, FlowNode, FlowEdge, FlowNodeData, FlowStatus } from '@/types/flow.types';
import type { BackendFlowGraph, BackendNode, BackendNodeType, BackendContract, BackendEdge } from './flowApi';

// ─── Contract defaults ────────────────────────────────────────────────

/**
 * A permissive, empty-blast-radius default contract. The graph-IR `contract` is
 * required on every graph (input/output schema, applies_when, permission envelope,
 * limits) but the canvas has no way to derive a real permission envelope or I/O schema
 * for a hand-drawn Flow -- that derivation is `huf.ai.graph.permissions.compute_static_envelope`'s
 * job, run server-side against the actual node configs once the tool/agent registry is
 * reachable. This default keeps a freshly drawn Flow schema-valid (empty envelope,
 * generous but finite limits) until a real permission-authoring UI exists; a Flow that
 * needs elevated read/write/http/code permissions still has to have those added to its
 * `contract.permission_envelope` by hand today.
 */
export function defaultContract(): BackendContract {
    return {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
            max_nodes: 200,
            max_rows: 10_000,
            max_output_bytes: 1_000_000,
            max_parallel_calls: 4,
            max_foreach_iterations: 1_000,
            max_external_calls: 200,
            max_writes: 100,
            max_wall_time_ms: 5 * 60 * 1000,
            fail_closed: true,
        },
    };
}

/**
 * A non-cryptographic, deterministic placeholder fingerprint. The graph-IR schema only
 * checks the *shape* of `fingerprint` (64 lowercase hex chars, graph-ir.md section 7) --
 * it does not itself recompute and compare it against the graph's canonical form, so a
 * stable placeholder is schema-valid. A real content-addressed fingerprint (matching
 * `huf.ai.procedure_versioning.compute_fingerprint`'s algorithm) is intentionally left
 * as backend-computed, not duplicated in the frontend.
 */
function placeholderFingerprint(seed: string): string {
    let h1 = 0xdeadbeef;
    let h2 = 0x41c6ce57;
    for (let i = 0; i < seed.length; i++) {
        const ch = seed.charCodeAt(i);
        h1 = Math.imul(h1 ^ ch, 2654435761);
        h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = (h1 ^ (h1 >>> 16)) >>> 0;
    h2 = (h2 ^ (h2 >>> 16)) >>> 0;
    const hex = (h1.toString(16).padStart(8, '0') + h2.toString(16).padStart(8, '0')).repeat(4);
    return hex.slice(0, 64);
}

// ─── Frontend → Backend ──────────────────────────────────────────────

/**
 * Convert a frontend Flow object into the backend graph JSON.
 */
export function serializeFlow(flow: Flow): BackendFlowGraph {
    const entryNode = flow.nodes.find(
        (n) => n.data?.nodeType === 'trigger'
    );

    // Outgoing edges per source node id, used to derive each node's own next/on_error/
    // self-routing pointers below -- the graph-IR has no independent edge list.
    const outgoingBySource = new Map<string, FlowEdge[]>();
    for (const edge of flow.edges) {
        const list = outgoingBySource.get(edge.source) ?? [];
        list.push(edge);
        outgoingBySource.set(edge.source, list);
    }

    return {
        schema_version: '1.0.0',
        profile: 'flow',
        fingerprint: placeholderFingerprint(JSON.stringify(flow.nodes.map((n) => n.id))),
        entry: entryNode?.id || flow.nodes[0]?.id || '',
        nodes: flow.nodes.map((node) => serializeNode(node, outgoingBySource.get(node.id) ?? [])),
        contract: defaultContract(),
    };
}

/** Which routing outcome a React Flow edge represents, read off its own data. */
function edgeOutcome(edge: FlowEdge): 'always' | 'on_success' | 'on_failure' | 'expression' {
    const data = edge.data as Record<string, unknown> | undefined;
    return (data?.edgeType as BackendEdge['type']) || 'always';
}

function serializeNode(node: FlowNode, outgoing: FlowEdge[]): BackendNode {
    const backendType = mapFrontendNodeTypeToBackend(node);
    const config = extractNodeConfig(node, backendType, outgoing);

    const successEdge = outgoing.find((e) => edgeOutcome(e) !== 'on_failure') ?? outgoing[0];
    const failureEdge = outgoing.find((e) => edgeOutcome(e) === 'on_failure');

    const base: BackendNode = {
        id: node.id,
        type: backendType,
        config,
        _position: node.position,
        _label: node.data?.label,
        _icon: node.data?.icon,
    };

    // condition/router.llm/human.approval carry their branch targets inside their own
    // config (on_true/on_false, options/default, approve_next/reject_next) rather than
    // a single linear `next` -- see extractNodeConfig. Every other node type routes
    // through `next` (its "always"/"on_success" outgoing edge, if any).
    if (backendType !== 'condition' && backendType !== 'router.llm' && backendType !== 'human.approval') {
        base.next = successEdge?.target ?? null;
    }
    if (failureEdge) {
        base.on_error = failureEdge.target;
    }

    return base;
}

function mapFrontendNodeTypeToBackend(node: FlowNode): BackendNodeType {
    const nodeType = node.data?.nodeType;

    // The shared IR's Flow profile has no "end" node type -- FlowNode's terminal shape
    // is "output" (NodeCommon with no `next`). See graph_ir.schema.json OutputNode.
    if (nodeType === 'end') return 'output';

    if (nodeType === 'trigger') {
        const triggerType = node.data?.triggerConfig?.type;
        if (triggerType === 'schedule') return 'trigger.schedule';
        if (triggerType === 'doc-event') return 'trigger.doc-event';
        return 'trigger.webhook';
    }

    // Action nodes — map by actionConfig.type
    const actionType = node.data?.actionConfig?.type;
    switch (actionType) {
        case 'agent-run': return 'agent.run';
        case 'tool-call': return 'tool.call';
        case 'router': return 'router.llm';
        case 'human.approval': return 'human.approval';
        case 'condition': return 'condition';
        case 'http-request': return 'http_request';
        case 'transform': return 'transform';
        case 'loop': return 'loop';
        default: return 'tool.call'; // fallback for unmapped action types
    }
}

/** Strip the `type` discriminator from a config object — backend infers type from node.type */
function omitType<T extends { type?: string }>(obj: T): Omit<T, 'type'> {
    const rest = { ...obj };
    delete rest.type;
    return rest;
}

function extractNodeConfig(
    node: FlowNode,
    backendType: BackendNodeType,
    outgoing: FlowEdge[]
): Record<string, unknown> {
    const data = node.data;
    let config: Record<string, unknown> = {};

    if (data?.triggerConfig && data.triggerConfig.type) {
        config = omitType(data.triggerConfig) as Record<string, unknown>;
    } else if (data?.actionConfig && data.actionConfig.type) {
        config = omitType(data.actionConfig) as Record<string, unknown>;
    }

    // Self-routing node types fold their outgoing edges into their own config, per the
    // shared IR (graph_ir.schema.json ConditionNode/RouterLlmNode/HumanApprovalNode).
    if (backendType === 'condition') {
        const trueEdge = outgoing.find((e) => (e.data as Record<string, unknown> | undefined)?.condition !== 'false');
        const falseEdge = outgoing.find((e) => e !== trueEdge);
        config.on_true = (config.on_true as string | undefined) ?? trueEdge?.target;
        config.on_false = (config.on_false as string | undefined) ?? falseEdge?.target;
    } else if (backendType === 'router.llm') {
        const options = (config.options as Array<{ label: string; node_id: string }> | undefined)
            ?? outgoing.map((e) => ({ label: (e.label as string) || e.target, node_id: e.target }));
        config.options = options;
        config.default = (config.default as string | undefined) ?? outgoing[0]?.target;
    } else if (backendType === 'human.approval') {
        const approveEdge = outgoing.find((e) => edgeOutcome(e) !== 'on_failure') ?? outgoing[0];
        const rejectEdge = outgoing.find((e) => edgeOutcome(e) === 'on_failure');
        config.approve_next = (config.approve_next as string | undefined) ?? approveEdge?.target;
        config.reject_next = (config.reject_next as string | undefined) ?? rejectEdge?.target;
    }

    return config;
}

// ─── Backend → Frontend ──────────────────────────────────────────────

/**
 * Convert a backend graph JSON into a frontend Flow object.
 */
export function deserializeFlow(
    flowId: string,
    flowName: string,
    status: string,
    graph: BackendFlowGraph
): Flow {
    // Auto-layout nodes if positions aren't stored
    const nodes = graph.nodes.map((node, index) =>
        deserializeNode(node, index)
    );

    return {
        id: flowId,
        name: flowName,
        status: mapBackendStatusToFrontend(status),
        nodes,
        edges: graph.nodes.flatMap(deserializeEdgesForNode),
        createdAt: new Date(),
        updatedAt: new Date(),
        // The graph-IR carries no per-graph `version`/`settings` any more -- version
        // lives on the Flow Definition doctype record, and run settings (mode,
        // max_hops, conversation_mode) are now engine-side defaults
        // (huf.ai.flow_engine.DEFAULT_MAX_HOPS et al.) rather than authored per-Flow.
        version: 1,
    };
}

function deserializeNode(node: BackendNode, index: number): FlowNode {
    // Use stored position, or auto-layout vertically
    const position = node._position || { x: 250, y: index * 150 };

    return {
        id: node.id,
        type: mapBackendNodeTypeToFrontend(node.type),
        position,
        data: buildNodeData(node),
    };
}

function mapBackendNodeTypeToFrontend(
    backendType: string
): string {
    if (backendType === 'output') return 'end';
    if (backendType.startsWith('trigger.')) return 'trigger';
    return 'action';
}

function buildNodeData(node: BackendNode): FlowNodeData {
    const frontendType = mapBackendNodeTypeToFrontend(node.type);

    const base: FlowNodeData = {
        label: node._label || getDefaultLabel(node.type),
        nodeType: frontendType as FlowNodeData['nodeType'],
        icon: node._icon || getDefaultIcon(node.type),
        configured: true,
    };

    if (frontendType === 'trigger') {
        const triggerType =
            node.type === 'trigger.schedule'
                ? ('schedule' as const)
                : node.type === 'trigger.doc-event'
                    ? ('doc-event' as const)
                    : ('webhook' as const);
        base.triggerConfig = {
            type: triggerType,
            ...node.config,
        } as FlowNodeData['triggerConfig'];
    } else if (frontendType === 'action') {
        base.actionConfig = {
            type: mapBackendActionType(node.type),
            ...node.config,
        } as FlowNodeData['actionConfig'];
    }

    return base;
}

function getDefaultLabel(backendType: string): string {
    const labels: Record<string, string> = {
        'trigger.webhook': 'Webhook trigger',
        'trigger.schedule': 'Schedule trigger',
        'trigger.doc-event': 'Document event trigger',
        'agent.run': 'Run agent',
        'tool.call': 'Call tool',
        'router.llm': 'LLM router',
        'human.approval': 'Human approval',
        'condition': 'Condition (IF)',
        'http_request': 'HTTP request',
        'transform': 'Transform data',
        'loop': 'Loop',
        'output': 'End',
    };
    return labels[backendType] || backendType;
}

function getDefaultIcon(backendType: string): string {
    const icons: Record<string, string> = {
        'trigger.webhook': 'Webhook',
        'trigger.schedule': 'Clock',
        'trigger.doc-event': 'Database',
        'agent.run': 'Bot',
        'tool.call': 'Play',
        'router.llm': 'GitBranch',
        'human.approval': 'UserCheck',
        'condition': 'GitBranch',
        'http_request': 'Globe',
        'transform': 'Repeat',
        'loop': 'RotateCw',
        'output': 'CheckCircle2',
    };
    return icons[backendType] || 'Play';
}

function mapBackendActionType(backendType: string): string {
    const map: Record<string, string> = {
        'agent.run': 'agent-run',
        'tool.call': 'tool-call',
        'router.llm': 'router',
        'human.approval': 'human.approval',
        'condition': 'condition',
        'http_request': 'http-request',
        'transform': 'transform',
        'loop': 'loop',
    };
    return map[backendType] || 'tool-call';
}

export function mapBackendStatusToFrontend(status: string): FlowStatus {
    const map: Record<string, FlowStatus> = {
        'Draft': 'draft',
        'Active': 'active',
        'Archived': 'paused',
    };
    return map[status] || 'draft';
}

/** Reconstruct this node's outgoing React Flow edge(s) from its own next/on_error/
 * self-routing config -- the inverse of serializeNode's folding. */
function deserializeEdgesForNode(node: BackendNode): FlowEdge[] {
    const edges: FlowEdge[] = [];

    const push = (to: string | null | undefined, outcome: BackendEdge['type'], label?: string) => {
        if (!to) return;
        edges.push({
            id: `${node.id}->${to}`,
            source: node.id,
            target: to,
            type: 'default',
            label,
            data: { edgeType: outcome },
        });
    };

    if (node.type === 'condition') {
        const cfg = node.config as { on_true?: string; on_false?: string };
        push(cfg.on_true, 'expression', 'true');
        push(cfg.on_false, 'expression', 'false');
    } else if (node.type === 'router.llm') {
        const cfg = node.config as { options?: Array<{ label: string; node_id: string }> };
        for (const option of cfg.options ?? []) {
            push(option.node_id, 'expression', option.label);
        }
    } else if (node.type === 'human.approval') {
        const cfg = node.config as { approve_next?: string; reject_next?: string };
        push(cfg.approve_next, 'on_success', 'approved');
        push(cfg.reject_next, 'on_failure', 'rejected');
    } else {
        push(node.next, 'always');
    }

    if (node.on_error) {
        push(node.on_error, 'on_failure');
    }

    return edges;
}
