import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import { flowService } from '../services/flowService';
import type { Flow } from '../types/flow.types';

interface Deps {
  activeFlowRef: MutableRefObject<Flow | null>;
  lastSyncedFlowRef: MutableRefObject<Flow | null>;
  setActiveFlowState: Dispatch<SetStateAction<Flow | null>>;
  markUnsaved: () => void;
}

/** Choose the step that runs when a step fails and has no failure path of its own (undefined = off). */
export function useErrorHandlerSetting({ activeFlowRef, lastSyncedFlowRef, setActiveFlowState, markUnsaved }: Deps) {
  return useCallback((nodeId: string | undefined) => {
    const prev = activeFlowRef.current;
    if (!prev || prev.errorHandler === nodeId) return;
    const updated: Flow = { ...prev, errorHandler: nodeId };
    if (nodeId === undefined) delete updated.errorHandler;
    activeFlowRef.current = updated;
    lastSyncedFlowRef.current = updated;
    setActiveFlowState(updated);
    flowService.setErrorHandler(prev.id, nodeId);
    markUnsaved();
  }, [activeFlowRef, lastSyncedFlowRef, setActiveFlowState, markUnsaved]);
}
