import type { UIEvent } from 'react';
import { useEffect, useRef } from 'react';
import { MiniMap, useReactFlow, useStore, useStoreApi, getNodesBounds } from 'reactflow';
import { isInView, panToReveal } from '@/lib/flow/flowLayout';

/** Fit-to-view never zooms in past 100% (a 3-step flow stays at normal size) nor out past 25%. */
export const FIT_VIEW_OPTIONS = { padding: 0.3, maxZoom: 1, minZoom: 0.25 } as const;

/** Narrowest canvas (px) that still has room for the overview next to the toolbar buttons. */
const MINIMAP_MIN_CANVAS_WIDTH = 640;

const MINIMAP_STYLE = {
  width: 200,
  height: 130,
  marginLeft: 58,
  marginBottom: 12,
  borderRadius: 8,
  border: '1px solid var(--border)',
  boxShadow: '0 1px 3px color-mix(in srgb, var(--foreground) 12%, transparent)',
} as const;

/** Overview map: drag its rectangle or click anywhere on it to move the canvas there; scroll on it to zoom. */
export function FlowMiniMap() {
  const { setCenter, getZoom } = useReactFlow();
  // In a narrow canvas (side panel open on a small window) the overview would sit under the top-right buttons.
  const canvasWidth = useStore((s) => s.width);
  if (canvasWidth && canvasWidth < MINIMAP_MIN_CANVAS_WIDTH) return null;
  return (
    <MiniMap
      position="bottom-left"
      ariaLabel="Flow overview"
      pannable
      zoomable
      onClick={(_event, position) => setCenter(position.x, position.y, { zoom: getZoom() })}
      nodeColor={(node) => {
        if (node.type === 'trigger') return 'var(--primary)';
        if (node.type === 'end') return 'var(--good)';
        return 'var(--muted)';
      }}
      className="!bg-background !border-border"
      data-testid="flow-minimap"
      // Sits to the right of the zoom controls (bottom-left), big enough to read, and can be dragged and zoomed.
      style={MINIMAP_STYLE}
    />
  );
}

/**
 * After a step or connection is removed, or Tidy layout / its Undo moves the steps, fits the whole graph in view,
 * but only when something would otherwise be out of sight (an orphaned "Add step" card, a step moved off screen).
 * When a step is added, the view only pans (zoom unchanged) if the new step or its "Add step" card would be cut off.
 */
export function FitViewAfterRemovalOrLayout({ flowId, nodeCount, edgeCount, layoutRevision }: { flowId?: string; nodeCount: number; edgeCount: number; layoutRevision: number }) {
  const { fitView, getNodes, getViewport, setViewport } = useReactFlow();
  const store = useStoreApi();
  const last = useRef<{ flowId?: string; nodeCount: number; edgeCount: number; layoutRevision: number } | null>(null);
  const knownIds = useRef<Set<string>>(new Set());
  useEffect(() => {
    const previous = last.current;
    last.current = { flowId, nodeCount, edgeCount, layoutRevision };
    // Ids as of the last settled view; the canvas store catches up with a change a moment after props change.
    const before = knownIds.current;
    const remember = () => { knownIds.current = new Set(getNodes().map((n) => n.id)); };
    // The first render of a flow is fitted by <ReactFlow fitView>; only later edits come here.
    if (!previous || previous.flowId !== flowId) {
      const settle = setTimeout(remember, 400);
      return () => clearTimeout(settle);
    }
    if (nodeCount > previous.nodeCount && edgeCount >= previous.edgeCount) {
      const timer = setTimeout(() => {
        const { width, height } = store.getState();
        const fresh = getNodes().filter((n) => !before.has(n.id));
        remember();
        if (fresh.length === 0 || width <= 0 || before.size === 0) return;
        // A card that has not been measured yet counts with the usual card size.
        const rects = fresh.map((n) => ({ x: n.position.x, y: n.position.y, width: n.width ?? 236, height: n.height ?? 62 }));
        const left = Math.min(...rects.map((r) => r.x));
        const top = Math.min(...rects.map((r) => r.y));
        const bounds = { x: left, y: top, width: Math.max(...rects.map((r) => r.x + r.width)) - left, height: Math.max(...rects.map((r) => r.y + r.height)) - top };
        const next = panToReveal(bounds, getViewport(), { width, height });
        if (next) setViewport({ ...next, zoom: getViewport().zoom }, { duration: 200 });
      }, 150);
      return () => clearTimeout(timer);
    }
    const removed = nodeCount < previous.nodeCount || edgeCount < previous.edgeCount;
    if (!removed && layoutRevision === previous.layoutRevision) return;
    const timer = setTimeout(() => {
      const nodes = getNodes();
      const { width, height } = store.getState();
      if (nodes.length > 0 && width > 0 && isInView(getNodesBounds(nodes), getViewport(), { width, height })) return;
      fitView({ ...FIT_VIEW_OPTIONS, duration: 200 });
    }, 60);
    return () => clearTimeout(timer);
  }, [flowId, nodeCount, edgeCount, layoutRevision, fitView, getNodes, getViewport, setViewport, store]);
  return null;
}

/**
 * The canvas is an overflow:hidden box. When something inside it takes focus while it is off screen (a newly added
 * step, the control a closed dialog returns focus to), the browser scrolls that hidden box to reveal it, which drags
 * the controls, minimap and toolbar out of place. The view is moved with the viewport transform only, so undo it.
 */
export function keepCanvasUnscrolled(event: UIEvent<HTMLDivElement>) {
  const el = event.currentTarget;
  if (el.scrollTop !== 0) el.scrollTop = 0;
  if (el.scrollLeft !== 0) el.scrollLeft = 0;
}
