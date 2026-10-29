import { useEffect, useState } from 'react';
import { flowService } from '../../../services/flowService';
import { edgeRoute } from '../../../services/flowSerializer';
import { onEdgeAction } from '@/lib/flow-graph/edgeActions';
import type { FlowEdgeRoute } from '../../../types/flow.types';

/** Keyboard undo (Cmd/Ctrl+Z). Skipped while focus is in a text field so it doesn't fight the input's own native undo. */
export function useUndoShortcut(undo: () => void, canUndo: boolean) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isUndoCombo = (e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'z';
      if (!isUndoCombo) return;

      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      const isEditable = tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable;
      if (isEditable || !canUndo) return;

      e.preventDefault();
      undo();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undo, canUndo]);
}

/**
 * Persistent "was this saved as a Procedure?" indicator -- the save-time toast is one-shot, so without this a
 * user who saved with the checkbox on and then closed the toast has no way to tell whether a Procedure exists.
 * Re-checked after every save completes (saveState -> 'saved'), not just on version bump: the auto-convert
 * checkbox's own conversion can complete slightly after the flow doc save itself resolves.
 */
export function useConvertedProcedure(flowId: string | undefined, version: unknown, saveState: unknown): string | null {
  const [convertedProcedure, setConvertedProcedure] = useState<string | null>(null);
  useEffect(() => {
    if (!flowId) {
      setConvertedProcedure(null);
      return;
    }
    let cancelled = false;
    flowService.getConversionStatus(flowId).then((status) => {
      if (!cancelled) setConvertedProcedure(status.converted_procedure);
    }).catch(() => {
      if (!cancelled) setConvertedProcedure(null);
    });
    return () => {
      cancelled = true;
    };
  }, [flowId, version, saveState]);
  return convertedProcedure;
}

/** Runs the "Add a step here" / "Remove connection" buttons of the connection panel on the canvas. */
export function useEdgeActions(edges: Array<{ id: string; source: string; data?: unknown; sourceHandle?: string | null }>, onInsert: (sourceNodeId: string, route: FlowEdgeRoute) => void, onRemove: (edgeId: string) => void) {
  useEffect(
    () =>
      onEdgeAction(({ type, edgeId }) => {
        const edge = edges.find((e) => e.id === edgeId);
        if (!edge) return;
        if (type === 'remove') onRemove(edgeId);
        else onInsert(edge.source, edgeRoute(edge as Parameters<typeof edgeRoute>[0]));
      }),
    [edges, onInsert, onRemove],
  );
}
