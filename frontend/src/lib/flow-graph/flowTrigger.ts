/**
 * Doc events a Flow trigger can use: the Flow graph IR enum (graph_ir.schema.json
 * TriggerDocEventNode.config.event). The trigger lives in the node config and is bound when the flow is published.
 */
export const DOC_EVENTS = ['after_insert', 'on_update', 'on_submit', 'on_cancel', 'on_trash'] as const;
export type FlowDocEvent = (typeof DOC_EVENTS)[number];
