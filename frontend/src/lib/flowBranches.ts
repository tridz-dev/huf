/**
 * Branching nodes are driven by their outgoing edges, not by node-id selects.
 *
 * Edge convention shared with the serializer: a connection leaving a branching node carries
 * `sourceHandle` = one of the handle ids below (and a matching `label`). The serializer folds them into
 * the contract fields: condition -> on_true / on_false; human.approval -> approve_next / reject_next /
 * timeout_next; foreach -> body (first node of the chain) / next (done edge). LLM Router edges have no
 * fixed handle: each outgoing edge's `label` is an option label and `config.default` names one target.
 */
export interface BranchHandle {
  id: string;
  label: string;
  /** Edge label written on the connection. */
  edgeLabel: string;
}

const CONDITION: BranchHandle[] = [
  { id: 'true', label: 'True', edgeLabel: 'true' },
  { id: 'false', label: 'False', edgeLabel: 'false' },
];
const HUMAN: BranchHandle[] = [
  { id: 'approve', label: 'Approved', edgeLabel: 'approved' },
  { id: 'reject', label: 'Rejected', edgeLabel: 'rejected' },
];
const HUMAN_TIMEOUT: BranchHandle = { id: 'timeout', label: 'Timed out', edgeLabel: 'timed out' };
const LOOP: BranchHandle[] = [
  { id: 'body', label: 'For each item', edgeLabel: 'for each item' },
  { id: 'done', label: 'When done', edgeLabel: 'when done' },
];

/** Handles for an action config (`type` is the UI discriminator). */
export function branchHandlesFor(actionType: string | undefined, config?: Record<string, unknown>): BranchHandle[] {
  switch (actionType) {
    case 'condition':
      return CONDITION;
    case 'human.approval':
      return config && config.timeout_ms ? [...HUMAN, HUMAN_TIMEOUT] : HUMAN;
    case 'loop':
      return LOOP;
    default:
      return [];
  }
}

export function handleLabel(actionType: string | undefined, handleId: string | null | undefined): string | undefined {
  return branchHandlesFor(actionType, { timeout_ms: 1 }).find((h) => h.id === handleId)?.edgeLabel;
}
