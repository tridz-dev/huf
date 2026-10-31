import { useEffect, useRef } from 'react';
import type { Edge, Node } from 'reactflow';
import { isArrowKey, nextStepFor } from '@/lib/flow-canvas/keyNav';
import { RENDER_ONLY_NODE_PREFIX } from '@/lib/flow-graph/flowCanvasGraph';

/**
 * Arrow keys on a focused step move focus to the step it connects to (Down: next, Up: previous, Left/Right: neighbour on the
 * row) instead of nudging the step; Enter then opens its settings (React Flow selects on Enter) and Alt+Arrow still nudges it.
 * Down from a step with nothing after it lands on its "Add step" card.
 */
export function useArrowNavigation(nodes: Node[], edges: Edge[]) {
  const latest = useRef({ nodes, edges });
  latest.current = { nodes, edges };
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!isArrowKey(e.key) || e.altKey || e.metaKey || e.ctrlKey || e.shiftKey) return;
      const el = e.target as HTMLElement | null;
      // Only when the step card itself has focus (not a button or field inside it), on the canvas.
      if (!el || !el.classList.contains('react-flow__node') || !el.closest('[data-testid="flow-canvas"]')) return;
      const id = el.getAttribute('data-id');
      if (!id || id.startsWith(RENDER_ONLY_NODE_PREFIX)) return;
      const { nodes: steps, edges: links } = latest.current;
      const real = steps.filter((n) => !n.id.startsWith(RENDER_ONLY_NODE_PREFIX));
      const next = nextStepFor(e.key, id, real, links);
      const target = next
        ? el.parentElement?.querySelector<HTMLElement>(`.react-flow__node[data-id="${CSS.escape(next)}"]`)
        : e.key === 'ArrowDown'
          ? el.closest('[data-testid="flow-canvas"]')?.querySelector<HTMLElement>(`[data-testid^="flow-add-step-${CSS.escape(id)}"]`)
          : null;
      // Handled either way: an arrow with nowhere to go must not push the step around.
      e.preventDefault();
      e.stopPropagation();
      target?.focus();
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, []);
}
