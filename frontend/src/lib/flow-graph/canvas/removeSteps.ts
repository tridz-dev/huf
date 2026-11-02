import { removeStep, type FlowGraphLike, type RemoveStepMode } from '../../flow/flowEdit';

/**
 * Remove several steps in one go (Delete with a group of steps selected): each is taken out the way a single delete would,
 * in turn, so the steps around the group stay joined up. Ids that are already gone (taken with an earlier one) are skipped.
 */
export function removeSteps(graph: FlowGraphLike, nodeIds: string[], mode: RemoveStepMode = 'reconnect'): FlowGraphLike {
  let current = graph;
  for (const id of nodeIds) {
    if (!current.nodes.some((n) => n.id === id)) continue;
    current = removeStep(current, id, mode);
  }
  return current;
}
