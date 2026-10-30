import type { FlowEdgeRoute } from '../../types/flow.types';

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

/** The side panel asks the canvas to add a step on one outgoing path of a step (the Yes / No rows of a Condition). */
export interface AddStepRequest {
  sourceNodeId: string;
  route: FlowEdgeRoute;
}
const ADD_EVENT = 'flow-add-step';

export function requestAddStep(request: AddStepRequest): void {
  bus.dispatchEvent(new CustomEvent<AddStepRequest>(ADD_EVENT, { detail: request }));
}

export function onAddStepRequest(handler: (request: AddStepRequest) => void): () => void {
  const listener = (e: Event) => handler((e as CustomEvent<AddStepRequest>).detail);
  bus.addEventListener(ADD_EVENT, listener);
  return () => bus.removeEventListener(ADD_EVENT, listener);
}
