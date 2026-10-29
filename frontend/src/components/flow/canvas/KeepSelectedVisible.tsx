import { useEffect, useRef } from 'react';
import { useReactFlow, useStore } from 'reactflow';
import { panToReveal } from '@/lib/flow/flowLayout';

/** Marks a panel or sheet that sits over the right edge of the canvas, so the step that was just opened can be kept clear of it. */
export const FLOW_PANEL_ATTR = 'data-flow-sheet-panel';

/**
 * When a step is selected, or the canvas gets narrower because the step panel opened or was dragged wider, moves the view just
 * enough (zoom unchanged) that the selected step is fully visible in the part of the canvas no panel covers.
 */
export function KeepSelectedVisible({ selectedNodeId }: { selectedNodeId: string | null }) {
  const rf = useReactFlow();
  const rfRef = useRef(rf);
  rfRef.current = rf;
  const width = useStore((s) => s.width);
  const height = useStore((s) => s.height);
  useEffect(() => {
    if (!selectedNodeId || !width || !height) return;
    const timer = setTimeout(() => {
      const node = rfRef.current.getNode(selectedNodeId);
      if (!node) return;
      // A sheet laid over the canvas covers its right side; a docked panel has already narrowed the canvas itself.
      const covered = document.querySelector<HTMLElement>(`[${FLOW_PANEL_ATTR}]`)?.offsetWidth ?? 0;
      const visibleWidth = Math.max(width - covered, 200);
      const vp = rfRef.current.getViewport();
      const rect = {
        x: node.positionAbsolute?.x ?? node.position.x,
        y: node.positionAbsolute?.y ?? node.position.y,
        width: node.width ?? 236,
        height: node.height ?? 62,
      };
      const next = panToReveal(rect, vp, { width: visibleWidth, height });
      if (next) rfRef.current.setViewport({ ...next, zoom: vp.zoom }, { duration: 200 });
    }, 140);
    return () => clearTimeout(timer);
  }, [selectedNodeId, width, height]);
  return null;
}
