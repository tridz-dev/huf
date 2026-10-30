import { useEffect, useState } from 'react';
import { flowService } from '../../../services/flowService';
import { edgeRoute } from '../../../services/flowSerializer';
import { onEdgeAction } from '@/lib/flow-graph/edgeActions';
import type { FlowEdgeRoute } from '../../../types/flow.types';
import type { Node } from 'reactflow';
import { blendPositions, motionMs, runFrames } from '@/lib/flow-canvas/tween';

/** Length (ms) of the glide steps make to their places after Tidy layout (and its Undo). */
export const TIDY_GLIDE_MS = 320;

/**
 * Moves the steps from where they are to where `target` puts them, a frame at a time, then leaves them exactly on `target`.
 * Returns null (and does nothing) when the same steps are not on both sides, nothing moves, or motion is reduced: the
 * caller then just sets the target.
 */
export function glideNodes<T extends Node>(current: T[], target: T[], setNodes: (nodes: T[]) => void, onDone: () => void): (() => void) | null {
  const ms = motionMs(TIDY_GLIDE_MS);
  const same = current.length === target.length && target.every((n) => current.some((c) => c.id === n.id));
  const moved = same && target.some((n) => {
    const c = current.find((v) => v.id === n.id);
    return c && (c.position.x !== n.position.x || c.position.y !== n.position.y);
  });
  if (!moved || ms === 0) return null;
  const from = Object.fromEntries(current.map((n) => [n.id, n.position]));
  const to = Object.fromEntries(target.map((n) => [n.id, n.position]));
  return runFrames(ms, (t) => {
    const at = blendPositions(from, to, t);
    setNodes(t >= 1 ? target : target.map((n) => ({ ...n, position: at[n.id] })));
  }, onDone);
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
