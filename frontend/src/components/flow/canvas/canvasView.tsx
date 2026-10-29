import type { UIEvent } from 'react';
import { useEffect, useRef } from 'react';
import type { Node } from 'reactflow';
import type { ReactFlowInstance } from 'reactflow';
import { Controls, MiniMap, useNodesInitialized, useReactFlow, useStore, useStoreApi, getNodesBounds } from 'reactflow';
import { isInView, panToReveal } from '@/lib/flow/flowLayout';
import { RENDER_ONLY_NODE_PREFIX } from '@/lib/flow-graph/flowCanvasGraph';

/** Fit-to-view never zooms in past 100% (a 3-step flow stays at normal size) nor out past 25%. */
export const FIT_VIEW_OPTIONS = { padding: 0.3, maxZoom: 1, minZoom: 0.25 } as const;

/** Flows of at most this many steps are never fitted smaller than FIT_MIN_ZOOM (the view then starts at the top and scrolls). */
const READABLE_STEP_LIMIT = 15;
const FIT_MIN_ZOOM = 0.75;
/** Bigger flows are fitted whole but not smaller than this. */
const FIT_MIN_ZOOM_LARGE = 0.4;
/** Narrowest a flow is fitted to keep it from running off the sides. */
const FIT_MIN_ZOOM_NARROW = 0.5;
/** Room (px) above the flow for the buttons in the top-right corner, and at the sides and bottom. */
export const FIT_TOP_INSET = 64;
const FIT_SIDE_INSET = 40;
const FIT_BOTTOM_INSET = 24;

/** The overview is only worth its space once a flow has this many steps. */
const MINIMAP_MIN_STEPS = 8;
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

const realSteps = (nodes: Node[]) => nodes.filter((n) => !n.id.startsWith(RENDER_ONLY_NODE_PREFIX)).length;

/** Screen area (px, canvas origin) the zoom buttons and the overview hide at the bottom-left of the canvas. */
function coveredByOverlays(width: number, height: number, withMinimap: boolean) {
  const boxHeight = (withMinimap ? MINIMAP_STYLE.height + MINIMAP_STYLE.marginBottom : 110) + 8;
  const boxWidth = withMinimap && width >= MINIMAP_MIN_CANVAS_WIDTH ? MINIMAP_STYLE.marginLeft + MINIMAP_STYLE.width + 8 : MINIMAP_STYLE.marginLeft;
  return { x: 0, y: height - boxHeight, width: boxWidth, height: boxHeight };
}

/**
 * Fits the whole flow with room for the top-right buttons above it, at most 100% and (up to 15 steps) never below 75%.
 * When a step or "Add step" card would still sit under the zoom buttons or the overview in the bottom-left corner, fits
 * again with room for that corner under the content (a little smaller, nothing hidden).
 */
export function fitClearOfOverlays(rf: ReactFlowInstance, width: number, height: number, duration = 0) {
  const nodes = rf.getNodes();
  if (nodes.length === 0 || width <= 0) return;
  const steps = realSteps(nodes);
  const bounds = getNodesBounds(nodes);
  const minZoom = steps <= READABLE_STEP_LIMIT ? FIT_MIN_ZOOM : FIT_MIN_ZOOM_LARGE;
  const covered = coveredByOverlays(width, height, steps >= MINIMAP_MIN_STEPS);
  const fit = (reserveBottom: number) => {
    const availW = Math.max(width - 2 * FIT_SIDE_INSET, 1);
    const availH = Math.max(height - FIT_TOP_INSET - FIT_BOTTOM_INSET - reserveBottom, 1);
    const fitW = availW / bounds.width;
    let zoom = Math.min(1, Math.max(minZoom, Math.min(fitW, availH / bounds.height)));
    // Never cut the flow off at the sides (a phone is narrower than two branches): only its length may scroll.
    if (zoom > fitW) zoom = Math.max(fitW, FIT_MIN_ZOOM_NARROW);
    const x = (width - bounds.width * zoom) / 2 - bounds.x * zoom;
    const spare = availH - bounds.height * zoom;
    // Taller than the canvas at the smallest readable zoom: start at the top, the rest is a scroll away.
    const y = FIT_TOP_INSET + (spare > 0 ? Math.min(spare / 2, 24) : 0) - bounds.y * zoom;
    return { x, y, zoom };
  };
  const hidden = (vp: { x: number; y: number; zoom: number }) =>
    nodes.some((n) => {
      const left = (n.positionAbsolute?.x ?? n.position.x) * vp.zoom + vp.x;
      const top = (n.positionAbsolute?.y ?? n.position.y) * vp.zoom + vp.y;
      return left < covered.x + covered.width && left + (n.width ?? 236) * vp.zoom > covered.x && top < covered.y + covered.height && top + (n.height ?? 62) * vp.zoom > covered.y;
    });
  let vp = fit(0);
  if (hidden(vp)) vp = fit(covered.height + 16);
  rf.setViewport(vp, { duration });
}

/** Zoom buttons whose "fit view" also keeps the flow clear of the overview. */
export function FlowControls({ className }: { className?: string }) {
  const rf = useReactFlow();
  const store = useStoreApi();
  return <Controls fitViewOptions={FIT_VIEW_OPTIONS} className={className} onFitView={() => { const { width, height } = store.getState(); fitClearOfOverlays(rf, width, height); }} />;
}

/** Overview map: drag its rectangle or click anywhere on it to move the canvas there; scroll on it to zoom. */
export function FlowMiniMap({ stepCount }: { stepCount: number }) {
  const { setCenter, getZoom } = useReactFlow();
  // In a narrow canvas (side panel open on a small window) the overview would sit under the top-right buttons.
  const canvasWidth = useStore((s) => s.width);
  if (stepCount < MINIMAP_MIN_STEPS || (canvasWidth && canvasWidth < MINIMAP_MIN_CANVAS_WIDTH)) return null;
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
  const rf = useReactFlow();
  const rfRef = useRef(rf); // the instance may be a new object on every render: keep the pending first-fit timer alive
  rfRef.current = rf;
  const { getNodes, getViewport, setViewport } = rf;
  const store = useStoreApi();
  const last = useRef<{ flowId?: string; nodeCount: number; edgeCount: number; layoutRevision: number } | null>(null);
  const knownIds = useRef<Set<string>>(new Set());
  // The first fit of a flow, as soon as every step is measured (and once more a moment later, when the "Add step" cards have settled).
  const firstFitFor = useRef<string | undefined>(undefined);
  const initialized = useNodesInitialized();
  useEffect(() => {
    if (!flowId || !initialized || firstFitFor.current === flowId) return;
    firstFitFor.current = flowId;
    const fitNow = () => { const { width, height } = store.getState(); fitClearOfOverlays(rfRef.current, width, height); };
    fitNow();
    const timer = setTimeout(() => { if (firstFitFor.current === flowId) fitNow(); }, 350);
    return () => clearTimeout(timer);
  }, [flowId, initialized, store]);
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
        const next = panToReveal(bounds, getViewport(), { width, height }, undefined, coveredByOverlays(width, height, nodeCount >= MINIMAP_MIN_STEPS));
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
      const { width: w, height: h } = store.getState();
      fitClearOfOverlays(rfRef.current, w, h, 200);
    }, 60);
    return () => clearTimeout(timer);
  }, [flowId, nodeCount, edgeCount, layoutRevision, getNodes, getViewport, setViewport, store]);
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

/**
 * Marks exactly the step the side panel shows as selected. A pending field edit written to the flow just as another step is
 * clicked re-syncs the canvas from the flow (which carries no selection): the panel then showed the clicked step while the
 * canvas showed none selected, with no delete button on it and the keyboard focus lost.
 */
export function withSelection<T extends Node>(nodes: T[], selectedNodeId: string | null): T[] {
  return nodes.map((n) => ((n.selected ?? false) === (n.id === selectedNodeId) ? n : { ...n, selected: n.id === selectedNodeId }));
}

/**
 * When a step is selected while it sits under the buttons in the top-right corner (or above the top edge), moves the
 * view down just enough that the step and its delete button are clear of them.
 */
export function KeepSelectedClearOfToolbar({ selectedNodeId }: { selectedNodeId: string | null }) {
  const rf = useReactFlow();
  const rfRef = useRef(rf);
  rfRef.current = rf;
  useEffect(() => {
    if (!selectedNodeId) return;
    const timer = setTimeout(() => {
      const node = rfRef.current.getNode(selectedNodeId);
      if (!node) return;
      const vp = rfRef.current.getViewport();
      const top = (node.positionAbsolute?.y ?? node.position.y) * vp.zoom + vp.y;
      if (top < FIT_TOP_INSET - 8) rfRef.current.setViewport({ ...vp, y: vp.y + (FIT_TOP_INSET - top) }, { duration: 150 });
    }, 80);
    return () => clearTimeout(timer);
  }, [selectedNodeId]);
  return null;
}
