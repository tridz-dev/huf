import { useCallback, useMemo, useRef, useState } from 'react';
import { emptyHistory, nextRedoLabel, nextUndoLabel, recordChange, redoStep, undoStep, type HistoryState, type HistoryStep } from './history';
import type { GraphChange, GraphSnapshot } from './graphChange';

/**
 * The undo / redo history of the open flow as a hook: stable callbacks (the history itself lives in a ref, so recording an
 * edit never re-renders anything by itself) and a small piece of state that changes only when the buttons need to.
 */
export function useFlowHistory() {
  const ref = useRef<HistoryState>(emptyHistory());
  const [shown, setShown] = useState({ undo: 0, redo: 0, undoLabel: undefined as string | undefined, redoLabel: undefined as string | undefined });

  const publish = useCallback(() => {
    const s = ref.current;
    setShown((prev) => {
      const next = { undo: s.past.length, redo: s.future.length, undoLabel: nextUndoLabel(s), redoLabel: nextRedoLabel(s) };
      return prev.undo === next.undo && prev.redo === next.redo && prev.undoLabel === next.undoLabel && prev.redoLabel === next.redoLabel ? prev : next;
    });
  }, []);

  const record = useCallback((before: GraphSnapshot, after: GraphSnapshot, hint?: Partial<GraphChange>) => {
    const next = recordChange(ref.current, before, after, Date.now(), hint);
    if (next === ref.current) return;
    ref.current = next;
    publish();
  }, [publish]);

  const undo = useCallback((current: GraphSnapshot): HistoryStep => {
    const step = undoStep(ref.current, current, Date.now());
    ref.current = step.state;
    publish();
    return step;
  }, [publish]);

  const redo = useCallback((current: GraphSnapshot): HistoryStep => {
    const step = redoStep(ref.current, current, Date.now());
    ref.current = step.state;
    publish();
    return step;
  }, [publish]);

  const reset = useCallback(() => {
    ref.current = emptyHistory();
    publish();
  }, [publish]);

  return useMemo(
    () => ({ record, undo, redo, reset, canUndo: shown.undo > 0, canRedo: shown.redo > 0, undoLabel: shown.undoLabel, redoLabel: shown.redoLabel }),
    [record, undo, redo, reset, shown],
  );
}
