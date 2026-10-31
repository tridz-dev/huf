/** Lookup tables of the flow serializer (kept out of flowSerializer.ts, which is at its size limit). */

/**
 * Config keys that must be non-blank for a node to count as configured.
 * Mirrors the required string fields in graph_ir.schema.json.
 */
export const REQUIRED_CONFIG_KEYS: Partial<Record<string, string[]>> = {
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


export function getDefaultLabel(backendType: string): string {
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


export function getDefaultIcon(backendType: string): string {
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
