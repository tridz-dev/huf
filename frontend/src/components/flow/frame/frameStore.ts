import { useSyncExternalStore } from 'react';

/**
 * Small shared state of the step panel frame and the header checklist (UX-8 / UX-17):
 * which errors may be shown yet, which field to jump to, and whether the checklist is open.
 *
 * Kept outside FlowContext on purpose: it is view state only (nothing here is saved with the flow) and it must be
 * reachable from the header, the step panel and the form fields without threading props through every form.
 */
export interface FocusRequest {
  nodeId: string;
  field: string;
  /** Changes on every request, so asking for the same field twice still fires. */
  seq: number;
}

interface FrameState {
  /** Show every unfinished field's message now (a save/publish/run attempt, or "N things to finish" was clicked). */
  revealAll: boolean;
  /** Steps whose messages were asked for (jumping to a step from the checklist). */
  revealedNodes: ReadonlySet<string>;
  /** Fields the person has already been in and left, as `nodeId:field`. */
  touched: ReadonlySet<string>;
  focusRequest: FocusRequest | null;
  checklistOpen: boolean;
  /** Longer explanation of the open step, shown behind the (i) in the panel header. */
  hint: string | null;
}

const EMPTY: FrameState = {
  revealAll: false,
  revealedNodes: new Set(),
  touched: new Set(),
  focusRequest: null,
  checklistOpen: false,
  hint: null,
};

let state: FrameState = EMPTY;
let seq = 0;
const listeners = new Set<() => void>();

function set(next: Partial<FrameState>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

export function useFrame<T>(select: (s: FrameState) => T): T {
  return useSyncExternalStore(subscribe, () => select(state), () => select(EMPTY));
}

export const fieldKey = (nodeId: string, field: string) => `${nodeId}:${field}`;

/** A new flow was opened: forget what was shown for the previous one. */
export function resetFrame() {
  state = { ...EMPTY };
  listeners.forEach((l) => l());
}

export function touchField(nodeId: string, field: string) {
  const key = fieldKey(nodeId, field);
  if (state.touched.has(key)) return;
  set({ touched: new Set(state.touched).add(key) });
}

/** Show the messages of every unfinished field. */
export function revealAllIssues() {
  if (!state.revealAll) set({ revealAll: true });
}

export function revealNode(nodeId: string) {
  if (state.revealedNodes.has(nodeId)) return;
  set({ revealedNodes: new Set(state.revealedNodes).add(nodeId) });
}

export function isFieldRevealed(s: FrameState, nodeId: string, field: string): boolean {
  return s.revealAll || s.revealedNodes.has(nodeId) || s.touched.has(fieldKey(nodeId, field));
}

/** Ask the open step panel to scroll to and focus a field (switching to the right tab first). */
export function requestFocus(nodeId: string, field: string) {
  revealNode(nodeId);
  set({ focusRequest: { nodeId, field, seq: ++seq } });
}

export function clearFocusRequest(requestSeq: number) {
  if (state.focusRequest?.seq === requestSeq) set({ focusRequest: null });
}

export function setChecklistOpen(open: boolean) {
  if (state.checklistOpen !== open) set({ checklistOpen: open });
}

export function setStepHint(hint: string | null) {
  if (state.hint !== hint) set({ hint });
}

/** Test helper. */
export function getFrameState(): FrameState {
  return state;
}
