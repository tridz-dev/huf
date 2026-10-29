/**
 * Lets the connection panel in the side panel ask the canvas to insert a step on, or remove, the selected connection
 * (the canvas owns the step picker and the "Remove this connection?" question).
 */
export interface EdgeAction {
  type: 'insert' | 'remove';
  edgeId: string;
}

const bus = new EventTarget();
const EVENT = 'flow-edge-action';

export function requestEdgeAction(action: EdgeAction): void {
  bus.dispatchEvent(new CustomEvent<EdgeAction>(EVENT, { detail: action }));
}

export function onEdgeAction(handler: (action: EdgeAction) => void): () => void {
  const listener = (e: Event) => handler((e as CustomEvent<EdgeAction>).detail);
  bus.addEventListener(EVENT, listener);
  return () => bus.removeEventListener(EVENT, listener);
}
