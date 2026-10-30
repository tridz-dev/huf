import type { FlowNode } from '../../../types/flow.types';

/** Action kinds that can be turned off: one way in, one way out, so the flow can simply step over them. */
const SKIPPABLE = new Set(['agent-run', 'tool-call', 'transform', 'state-get', 'state-set', 'state-delete', 'doc-create', 'code-run']);

export function canDisableStep(node: Pick<FlowNode, 'data'>): boolean {
  return node.data.nodeType === 'action' && SKIPPABLE.has(String((node.data.actionConfig as { type?: unknown } | undefined)?.type ?? ''));
}

/** A trigger starts the flow, and a flow has one of them. */
export function canDuplicateStep(node: Pick<FlowNode, 'data'>): boolean {
  return node.data.nodeType !== 'trigger';
}
