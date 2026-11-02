/**
 * The editor's undo / redo history. A pure state machine over graph snapshots (steps + connections), so it can be tested
 * without React. `past` holds the states to return to on Undo, `future` the states to return to on Redo.
 *
 * - Bounded: at most HISTORY_LIMIT steps back.
 * - Grouped: edits of the same group made close together (typing in one field, dragging one step) are one step.
 * - A new edit after an Undo drops the Redo steps (they no longer follow from what is on screen).
 */
import { GROUP_WINDOW_MS, describeChange, type GraphChange, type GraphSnapshot } from './graphChange';

export const HISTORY_LIMIT = 100;

export interface HistoryEntry {
  /** The graph to go back to. */
  snapshot: GraphSnapshot;
  /** What the step did, in words ("Moved a step"). */
  label: string;
  group?: string;
  kind: GraphChange['kind'];
  /** When the last edit of this step happened (ms). */
  at: number;
}

export interface HistoryState {
  past: HistoryEntry[];
  future: HistoryEntry[];
  /** False right after an Undo / Redo: the next edit always starts a new step, never joins the top one. */
  open: boolean;
}

export const emptyHistory = (): HistoryState => ({ past: [], future: [], open: false });

/** Remember that the graph went from `before` to `after`. Returns the same state when nothing the author did changed. */
export function recordChange(state: HistoryState, before: GraphSnapshot, after: GraphSnapshot, now: number, hint?: Partial<GraphChange>): HistoryState {
  const change = describeChange(before, after, hint);
  if (!change) return state;
  const top = state.past[state.past.length - 1];
  const window = GROUP_WINDOW_MS[change.kind] ?? 0;
  if (state.open && top && change.group && top.group === change.group && now - top.at <= window) {
    // Same typing / same drag: the earlier "before" stays the place to go back to.
    const past = [...state.past.slice(0, -1), { ...top, at: now }];
    return { past, future: [], open: true };
  }
  const entry: HistoryEntry = { snapshot: before, label: change.label, group: change.group, kind: change.kind, at: now };
  return { past: [...state.past, entry].slice(-HISTORY_LIMIT), future: [], open: true };
}

export interface HistoryStep {
  state: HistoryState;
  /** The graph to show now; undefined when there is nothing to undo / redo. */
  snapshot?: GraphSnapshot;
  /** What was undone / redone. */
  label?: string;
}

/** Go back one step. `current` is the graph on screen now (it becomes the Redo target). */
export function undoStep(state: HistoryState, current: GraphSnapshot, now: number): HistoryStep {
  const top = state.past[state.past.length - 1];
  if (!top) return { state };
  const future: HistoryEntry[] = [...state.future, { ...top, snapshot: current, at: now }].slice(-HISTORY_LIMIT);
  return { state: { past: state.past.slice(0, -1), future, open: false }, snapshot: top.snapshot, label: top.label };
}

/** Go forward one step again. */
export function redoStep(state: HistoryState, current: GraphSnapshot, now: number): HistoryStep {
  const top = state.future[state.future.length - 1];
  if (!top) return { state };
  const past: HistoryEntry[] = [...state.past, { ...top, snapshot: current, at: now }].slice(-HISTORY_LIMIT);
  return { state: { past, future: state.future.slice(0, -1), open: false }, snapshot: top.snapshot, label: top.label };
}

export const nextUndoLabel = (state: HistoryState): string | undefined => state.past[state.past.length - 1]?.label;
export const nextRedoLabel = (state: HistoryState): string | undefined => state.future[state.future.length - 1]?.label;
