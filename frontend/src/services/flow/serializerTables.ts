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
  app: 'trigger.app',
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
  'trigger.app': ['app', 'entry_policy'],
  ...Object.fromEntries(GATEWAY_TRIGGER_KINDS.map((k) => [k.nodeType, ['gateway', 'entry_policy', 'params']])),
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
    'trigger.app': ['app'],
    ...Object.fromEntries(GATEWAY_TRIGGER_KINDS.map((k) => [k.nodeType, ['gateway']])),
    'agent.run': ['agent', 'prompt'],
    'tool.call': ['tool_id'],
    'router.llm': ['prompt'],
    'wait': ['mode'],
    'human.approval': ['message'],
    'condition': ['expression'],
    'foreach': ['items'],
    'validate': ['assertions'],
    'state.get': ['key'],
    'state.set': ['key'],
    'state.delete': ['key'],
    'doc.create': ['doctype'],
    'stop': ['message'],
    'doc.get': ['doctype'],
    'doc.update': ['doctype', 'name', 'values'],
    'flow.call': ['flow_id'],
    'member.set': ['vars'],
    'send.message': ['gateway', 'category'],
    'code.run': ['code', 'profile'],
    'transform': ['op'],
};


/** Title of a rules step while "Let AI choose the path" is on (the rules title comes from the palette). */
export const AI_CHOICE_TITLE = 'Let AI choose';

/**
 * Title a loaded step shows: the stored one, or the default when there is none or it is only the raw node type (as
 * some app-built flows store it). A rules step that lets AI choose is named for that unless the user renamed it.
 */
export function storedNodeTitle(type: string, label: unknown, config: Record<string, unknown> | undefined): string {
    const stored = typeof label === 'string' ? label.trim() : '';
    const fallback = getDefaultLabel(type);
    const decision = config?.decision;
    const aiChoice = type === 'router.decision' && decision !== null && typeof decision === 'object';
    if (!stored || stored === type) return aiChoice ? AI_CHOICE_TITLE : fallback;
    return aiChoice && stored === fallback ? AI_CHOICE_TITLE : stored;
}

export function getDefaultLabel(backendType: string): string {
    const labels: Record<string, string> = {
        'trigger.webhook': 'Webhook trigger',
        'trigger.schedule': 'Schedule trigger',
        'trigger.doc-event': 'Document event trigger',
        'trigger.gateway': 'Chat message',
        'trigger.whatsapp': 'WhatsApp message',
        'trigger.telegram': 'Telegram message',
        'trigger.app': 'App trigger',
        'trigger.unset': 'Select trigger',
        'agent.run': 'Run agent',
        'tool.call': 'Call tool',
        'router.llm': 'LLM router',
        'router.decision': 'Choose by rules',
        'wait': 'Wait',
        'human.approval': 'Human approval',
        'condition': 'Condition (IF)',
        'transform': 'Transform data',
        'foreach': 'Loop',
        'validate': 'Validate',
        'state.get': 'Get state',
        'state.set': 'Set state',
        'state.delete': 'Delete state',
        'doc.create': 'Create document',
        'stop': 'Stop with error',
        'doc.get': 'Find document',
        'doc.update': 'Update document',
        'flow.call': 'Run another flow',
        'member.set': 'Remember for this person',
        'send.message': 'Send message',
        'code.run': 'Execute code',
        'split': 'Split audience',
        'knowledge.search': 'Search knowledge',
        'handoff': 'Hand to a person',
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
        'trigger.app': 'AppWindow',
        'trigger.unset': 'CircleDashed',
        'agent.run': 'SquareAsterisk',
        'tool.call': 'Play',
        'router.llm': 'GitBranch',
        'router.decision': 'Split',
        'knowledge.search': 'BookOpen',
        'handoff': 'UserRound',
        'wait': 'Hourglass',
        'human.approval': 'UserCheck',
        'condition': 'GitBranch',
        'transform': 'Repeat',
        'foreach': 'RotateCw',
        'validate': 'ShieldCheck',
        'state.get': 'Database',
        'state.set': 'Save',
        'state.delete': 'Trash2',
        'doc.create': 'FilePlus',
        'stop': 'OctagonX',
        'doc.get': 'FileSearch',
        'doc.update': 'FilePen',
        'flow.call': 'Workflow',
        'member.set': 'UserPen',
        'send.message': 'Send',
        'code.run': 'Terminal',
        'split': 'Split',
        'output': 'CheckCircle2',
    };
    return icons[backendType] || 'Play';
}
