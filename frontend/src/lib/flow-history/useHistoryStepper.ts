import { useCallback } from 'react';
import { toast } from '@/lib/toast';
import type { Flow } from '../../types/flow.types';
import { announce } from './announce';
import type { GraphSnapshot } from './graphChange';
import type { HistoryStep } from './history';

interface Params {
  getFlow: () => Flow | null;
  undoStep: (current: GraphSnapshot) => HistoryStep;
  redoStep: (current: GraphSnapshot) => HistoryStep;
  /** Show this graph (the editor writes it back like any other edit, without recording it). */
  restore: (snapshot: GraphSnapshot) => void;
}

/** Undo and Redo: take a step from the history, show it, and say what happened (aria-live + a short toast). */
export function useHistoryStepper({ getFlow, undoStep, redoStep, restore }: Params) {
  const step = useCallback((direction: 'undo' | 'redo') => {
    const current = getFlow();
    if (!current) return;
    const graph = { nodes: current.nodes, edges: current.edges };
    const result = direction === 'undo' ? undoStep(graph) : redoStep(graph);
    if (!result.snapshot) return;
    restore(result.snapshot);
    const what = (result.label ?? 'the last change').replace(/^./, (c) => c.toLowerCase());
    const text = `${direction === 'undo' ? 'Undid' : 'Redid'}: ${what}`;
    announce(text);
    toast.dismiss(); // the toast of the action being undone ("Step duplicated") no longer applies
    toast(text, { id: 'flow-history-toast', duration: 2500 });
  }, [getFlow, undoStep, redoStep, restore]);
  return { undo: useCallback(() => step('undo'), [step]), redo: useCallback(() => step('redo'), [step]) };
}
