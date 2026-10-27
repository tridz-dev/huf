// Pure helpers for the flow builder's session-local undo history. A snapshot is
// the full nodes+edges pair captured before a destructive mutation; restoring it
// replays the exact prior edges, so a restored node never comes back dangling.

export interface FlowGraphSnapshot<N, E> {
  nodes: N[];
  edges: E[];
}

export function pushSnapshot<N, E>(
  stack: FlowGraphSnapshot<N, E>[],
  snapshot: FlowGraphSnapshot<N, E>,
  limit: number,
): FlowGraphSnapshot<N, E>[] {
  return [...stack, snapshot].slice(-limit);
}

export function popSnapshot<N, E>(
  stack: FlowGraphSnapshot<N, E>[],
): { snapshot: FlowGraphSnapshot<N, E> | undefined; rest: FlowGraphSnapshot<N, E>[] } {
  if (stack.length === 0) return { snapshot: undefined, rest: stack };
  return { snapshot: stack[stack.length - 1], rest: stack.slice(0, -1) };
}
