/**
 * Flow Serializer — Bidirectional conversion between React Flow format
 * and backend definition_json schema.
 *
 * Every save/load must go through serializeFlow / deserializeFlow.
 *
 * v0.2 — Updated to support new backend node types:
 *   condition, http_request, transform, loop
 */

import type { Flow, FlowNode, FlowEdge, FlowNodeData, FlowStatus } from '@/types/flow.types';
import type { BackendFlowGraph, BackendNode, BackendEdge } from './flowApi';

// ─── Frontend → Backend ──────────────────────────────────────────────

/**
 * Convert a frontend Flow object into the backend graph JSON.
 */
export function serializeFlow(flow: Flow): BackendFlowGraph {
    const entryNode = flow.nodes.find(
        (n) => n.data?.nodeType === 'trigger'
    );

    return {
        schema_version: 1,
        id: flow.id,
        version: flow.version,
        entry: entryNode?.id || flow.nodes[0]?.id || '',
        nodes: flow.nodes.map(serializeNode),
        edges: flow.edges.map(serializeEdge),
        settings: {
            mode: 'normal',
            max_hops: 100,
        },
        metadata: {
            name: flow.name,
            description: flow.description,
            category: flow.category,
        },
    };
}

function serializeNode(node: FlowNode): BackendNode {
    return {
        id: node.id,
        type: mapFrontendNodeTypeToBackend(node),
        config: extractNodeConfig(node),
        _position: node.position,
        _label: node.data?.label,
        _icon: node.data?.icon,
    };
}

function mapFrontendNodeTypeToBackend(node: FlowNode): BackendNode['type'] {
    const nodeType = node.data?.nodeType;

    if (nodeType === 'end') return 'end';

    if (nodeType === 'trigger') {
        return 'trigger.webhook';
    }

    // Action nodes — map by actionConfig.type
    const actionType = node.data?.actionConfig?.type;
    switch (actionType) {
        case 'agent-run': return 'agent.run';
        case 'tool-call': return 'tool.call';
        case 'router': return 'router.llm';
        case 'human-in-loop': return 'human.approval';
        case 'condition': return 'condition';
        case 'http-request': return 'http_request';
        case 'transform': return 'transform';
        case 'loop': return 'loop';
        default: return 'tool.call'; // fallback for unmapped action types
    }
}

/** Strip the `type` discriminator from a config object — backend infers type from node.type */
function omitType<T extends { type?: string }>(obj: T): Omit<T, 'type'> {
    const { type: _type, ...rest } = obj;
    return rest;
}

function extractNodeConfig(node: FlowNode): Record<string, unknown> {
    const data = node.data;
    if (!data) return {};

    if (data.triggerConfig && data.triggerConfig.type) {
        return omitType(data.triggerConfig) as Record<string, unknown>;
    }
    if (data.actionConfig && data.actionConfig.type) {
        return omitType(data.actionConfig) as Record<string, unknown>;
    }
    return {};
}

function serializeEdge(edge: FlowEdge): BackendEdge {
    const data = edge.data as Record<string, unknown> | undefined;
    return {
        id: edge.id,
        from: edge.source,
        to: edge.target,
        type: (data?.edgeType as BackendEdge['type']) || 'always',
        priority: (data?.priority as number) || 0,
        condition: data?.condition as string | undefined,
        meta: data?.meta as Record<string, unknown> | undefined,
    };
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
        description: graph.metadata?.description,
        status: mapBackendStatusToFrontend(status),
        category: graph.metadata?.category,
        nodes,
        edges: graph.edges.map(deserializeEdge),
        createdAt: new Date(),
        updatedAt: new Date(),
        version: graph.version,
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
    if (backendType === 'end') return 'end';
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
        base.triggerConfig = {
            type: 'webhook' as const,
            ...node.config,
        };
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
        'trigger.webhook': 'Webhook Trigger',
        'agent.run': 'Run Agent',
        'tool.call': 'Call Tool',
        'router.llm': 'LLM Router',
        'human.approval': 'Human Approval',
        'condition': 'Condition (IF)',
        'http_request': 'HTTP Request',
        'transform': 'Transform Data',
        'loop': 'Loop',
        'end': 'End',
    };
    return labels[backendType] || backendType;
}

function getDefaultIcon(backendType: string): string {
    const icons: Record<string, string> = {
        'trigger.webhook': 'Webhook',
        'agent.run': 'Bot',
        'tool.call': 'Play',
        'router.llm': 'GitBranch',
        'human.approval': 'UserCheck',
        'condition': 'GitBranch',
        'http_request': 'Globe',
        'transform': 'Repeat',
        'loop': 'RotateCw',
        'end': 'CheckCircle2',
    };
    return icons[backendType] || 'Play';
}

function mapBackendActionType(backendType: string): string {
    const map: Record<string, string> = {
        'agent.run': 'agent-run',
        'tool.call': 'tool-call',
        'router.llm': 'router',
        'human.approval': 'human-in-loop',
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

function deserializeEdge(edge: BackendEdge): FlowEdge {
    return {
        id: edge.id,
        source: edge.from,
        target: edge.to,
        type: 'default', // React Flow visual edge type
        data: {
            edgeType: edge.type,
            priority: edge.priority,
            condition: edge.condition,
            meta: edge.meta,
        },
    };
}
