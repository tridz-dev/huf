/** Lookup tables of the flow serializer (kept out of flowSerializer.ts, which is at its size limit). */

import type { TriggerType } from '@/types/flow.types';
import { GATEWAY_TRIGGER_KINDS } from '@/lib/flow-gateway/triggerKinds';

/**
 * Editor trigger kind -> graph-IR node type. The one place that decides it: a kind missing here is saved as
 * `trigger.unset` (never guessed to be a webhook).
 */
export const TRIGGER_TO_NODE_TYPE: Record<TriggerType, string> = {
  webhook: 'trigger.webhook',
  schedule: 'trigger.schedule',
  'doc-event': 'trigger.doc-event',
  ...Object.fromEntries(GATEWAY_TRIGGER_KINDS.map((k) => [k.id, k.nodeType])),
} as Record<TriggerType, string>;

/** Graph-IR trigger node type -> editor kind. An unknown `trigger.*` type loads as "not chosen yet", never as a webhook. */
export const NODE_TYPE_TO_TRIGGER: Record<string, TriggerType> = Object.fromEntries(
  Object.entries(TRIGGER_TO_NODE_TYPE).map(([kind, nodeType]) => [nodeType, kind as TriggerType])
);

/** Config keys each trigger node type may hold (anything else on the canvas config is dropped on save). */
export const TRIGGER_CONFIG_KEYS: Record<string, string[]> = {
  'trigger.webhook': ['method', 'secret'],
  'trigger.schedule': ['cron', 'time_zone'],
  'trigger.doc-event': ['doctype', 'event'],
  ...Object.fromEntries(GATEWAY_TRIGGER_KINDS.map((k) => [k.nodeType, ['gateway', 'params']])),
};

/** A chat trigger's saved config: the channel as typed, and `params` only while something is set. */
export function gatewayConfigOut(config: Record<string, unknown>): Record<string, unknown> {
  const out = { ...config };
  if (!Array.isArray(out.params) || out.params.length === 0) delete out.params;
  return out;
}

/**
 * Config keys that must be non-blank for a node to count as configured.
 * Mirrors the required string fields in graph_ir.schema.json.
 */
export const REQUIRED_CONFIG_KEYS: Partial<Record<string, string[]>> = {
    'trigger.webhook': ['method', 'secret'],
    'trigger.schedule': ['cron'],
    'trigger.doc-event': ['doctype', 'event'],
    ...Object.fromEntries(GATEWAY_TRIGGER_KINDS.map((k) => [k.nodeType, ['gateway']])),
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


export function getDefaultLabel(backendType: string): string {
    const labels: Record<string, string> = {
        'trigger.webhook': 'Webhook trigger',
        'trigger.schedule': 'Schedule trigger',
        'trigger.doc-event': 'Document event trigger',
        'trigger.gateway': 'Chat message',
        'trigger.whatsapp': 'WhatsApp message',
        'trigger.telegram': 'Telegram message',
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


export function getDefaultIcon(backendType: string): string {
    const icons: Record<string, string> = {
        'trigger.webhook': 'Webhook',
        'trigger.schedule': 'Clock',
        'trigger.doc-event': 'Database',
        'trigger.gateway': 'MessageSquare',
        'trigger.whatsapp': 'MessageCircle',
        'trigger.telegram': 'Send',
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
