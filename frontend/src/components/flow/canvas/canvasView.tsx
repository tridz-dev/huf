import type { UIEvent } from 'react';
import { useEffect, useRef } from 'react';
import type { Node } from 'reactflow';
import type { ReactFlowInstance } from 'reactflow';
import { Controls, MiniMap, useNodesInitialized, useReactFlow, useStore, useStoreApi, getNodesBounds } from 'reactflow';
import { isInView, panToReveal } from '@/lib/flow/flowLayout';
import { RENDER_ONLY_NODE_PREFIX } from '@/lib/flow-graph/flowCanvasGraph';
import { motionMs } from '@/lib/flow-canvas/tween';
import { TIDY_GLIDE_MS } from './useCanvasEffects';
import { FIT_MIN_READABLE, READABLE_STEP_LIMIT, ZOOM_MIN } from '@/lib/flow-canvas/zoomLod';

/** Fit-to-view never zooms in past 100% (a 3-step flow stays at normal size) nor out past the canvas minimum. */
export const FIT_VIEW_OPTIONS = { padding: 0.3, maxZoom: 1, minZoom: ZOOM_MIN } as const;

/** Flows of at most this many steps are never fitted smaller than FIT_MIN_ZOOM (the view then starts at the top and scrolls). */
const FIT_MIN_ZOOM = FIT_MIN_READABLE;
/** Bigger flows are fitted whole (down to the canvas minimum): the cards switch to icons and titles, so nothing is unreadable. */
const FIT_MIN_ZOOM_LARGE = ZOOM_MIN;
/** Narrowest a flow is fitted to keep it from running off the sides. */
const FIT_MIN_ZOOM_NARROW = 0.5;
const NARROW_CANVAS = 560;
const FIT_MIN_ZOOM_NARROW_LARGE = ZOOM_MIN;
/** Room (px) above the flow for the buttons in the top-right corner, and at the sides and bottom. */
export const FIT_TOP_INSET = 64;
const FIT_SIDE_INSET = 40;
const FIT_BOTTOM_INSET = 24;

/** The overview is only worth its space once a flow has this many steps. */
const MINIMAP_MIN_STEPS = 8;
/** Narrowest canvas (px) that still has room for the overview next to the toolbar buttons. */
const MINIMAP_MIN_CANVAS_WIDTH = 640;

/**
 * Classes of the canvas itself: bigger hit areas and a glow on the connection dots, a clear focus ring on the step that has
 * keyboard focus (on its card, not the invisible box around it), and the step under the pointer or focus drawn above its neighbours.
 */
const FOCUS_CARD = '[&_.react-flow__node:focus-visible_.flow-card]';
export const CANVAS_CLASS = [
  'bg-background w-full h-full',
  "[&_.react-flow__handle]:transition-shadow [&_.react-flow__handle]:after:absolute [&_.react-flow__handle]:after:-inset-2 [&_.react-flow__handle]:after:content-['']",
  '[&_.react-flow__handle:hover]:!bg-signal [&_.react-flow__handle:hover]:shadow-[0_0_0_4px_color-mix(in_srgb,var(--signal)_30%,transparent)]',
  '[&_.react-flow__node:focus-visible]:outline-none',
  `${FOCUS_CARD}:ring-2 ${FOCUS_CARD}:ring-signal ${FOCUS_CARD}:ring-offset-2 ${FOCUS_CARD}:ring-offset-background`,
  '[&_.react-flow__node:hover]:!z-[1000] [&_.react-flow__node:focus-visible]:!z-[1000]',
].join(' ');

const MINIMAP_STYLE = {
  width: 176,
  height: 112,
  // Clear of the zoom buttons (28 px wide, 10 px in): at least 20 px between them, and the same bottom edge as the buttons.
  marginLeft: 62,
  marginBottom: 24,
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

type View = { x: number; y: number; zoom: number };

/** The view moved right just far enough that no step sits under `covered`; unchanged when that would push the flow out of the canvas. */
export function shiftClearOfCorner(nodes: Node[], vp: View, covered: { x: number; y: number; width: number; height: number }, canvasWidth: number): View {
  const rect = (n: Node) => {
    const left = (n.positionAbsolute?.x ?? n.position.x) * vp.zoom + vp.x;
    const top = (n.positionAbsolute?.y ?? n.position.y) * vp.zoom + vp.y;
    return { left, right: left + (n.width ?? 236) * vp.zoom, top, bottom: top + (n.height ?? 62) * vp.zoom };
  };
  const rects = nodes.map(rect);
  const under = rects.filter((r) => r.left < covered.x + covered.width && r.right > covered.x && r.top < covered.y + covered.height && r.bottom > covered.y);
  if (under.length === 0) return vp;
  const dx = covered.x + covered.width + 12 - Math.min(...under.map((r) => r.left));
  // Left padding for the overview: the flow moves right until nothing sits under it. A wide flow may then reach past the right
  // edge (its branches were a pan away already), but not by more than half of its width: then the view is left alone.
  const flowLeft = Math.min(...rects.map((r) => r.left));
  const flowRight = Math.max(...rects.map((r) => r.right));
  const pastEdge = Math.max(0, flowRight + dx - (canvasWidth - 16));
  return dx > 0 && pastEdge <= (flowRight - flowLeft) / 2 ? { ...vp, x: vp.x + dx } : vp;
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
    // (Only a canvas too narrow for two branches: a wider one keeps the readable minimum and the rest is a pan away.)
    if (zoom > fitW && width < NARROW_CANVAS) zoom = Math.max(fitW, steps <= READABLE_STEP_LIMIT ? FIT_MIN_ZOOM_NARROW : FIT_MIN_ZOOM_NARROW_LARGE);
    let x = (width - bounds.width * zoom) / 2 - bounds.x * zoom;
    // Wider than the canvas at the readable zoom: keep the main line (the trigger and what follows it) in the middle; the branches are a pan away.
    if (bounds.width * zoom > availW) {
      const anchor = nodes.find((n) => n.type === 'trigger') ?? nodes[0];
      x = width / 2 - ((anchor.positionAbsolute?.x ?? anchor.position.x) + (anchor.width ?? 236) / 2) * zoom;
    }
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
  // Still under the corner: the readable zoom (15 steps or fewer) stops the flow from shrinking further, so make room at the side
  // instead (the content scrolls), as long as the flow stays in the canvas. Nothing is shrunk below the floor.
  if (hidden(vp)) vp = shiftClearOfCorner(nodes, vp, covered, width);
  rf.setViewport(vp, { duration: motionMs(duration) });
}

/** Zoom buttons whose "fit view" also keeps the flow clear of the overview. */
export function FlowControls({ className }: { className?: string }) {
  const rf = useReactFlow();
  const store = useStoreApi();
  return <Controls fitViewOptions={FIT_VIEW_OPTIONS} className={className} onFitView={() => { const { width, height } = store.getState(); fitClearOfOverlays(rf, width, height); }} />;
}

/** Colour of a step on the overview: its run result when a run is shown, else what kind of step it is. */
const minimapColor = (node: Node): string => {
  switch ((node.data as { status?: string } | undefined)?.status) {
    case 'error': return 'var(--destructive)';
    case 'success': return 'var(--good)';
    case 'running': return 'var(--signal)';
    case 'waiting': return 'var(--warning)';
    case 'skipped': return 'var(--steel-soft)';
    default: break;
  }
  if (node.type === 'trigger') return 'var(--primary)';
  if (node.type === 'end') return 'var(--good)';
  return 'var(--muted-foreground)';
};

/** A minimap click shorter than about one viewport glides this long; a longer one jumps (a long animated pan zooms out and back in). */
export const MINIMAP_GLIDE_MS = 150;

/** Length (ms) of the view change for a click `distancePx` (screen px) from the current centre in a canvas `viewportPx` across: 0 when far, or when motion is reduced. */
export function minimapMoveMs(distancePx: number, viewportPx: number): number {
  return distancePx < viewportPx ? motionMs(MINIMAP_GLIDE_MS) : 0;
}

/** Overview map: drag its rectangle or click anywhere on it to move the canvas there; scroll on it to zoom. */
export function FlowMiniMap({ stepCount }: { stepCount: number }) {
  const { setCenter, getZoom } = useReactFlow();
  const store = useStoreApi();
  // In a narrow canvas (side panel open on a small window) the overview would sit under the top-right buttons.
  const canvasWidth = useStore((s) => s.width);
  if (stepCount < MINIMAP_MIN_STEPS || (canvasWidth && canvasWidth < MINIMAP_MIN_CANVAS_WIDTH)) return null;
  return (
    <MiniMap
      position="bottom-left"
      ariaLabel="Flow overview"
      pannable
      zoomable
      // A short move glides; a long one jumps (the animated pan zooms out and back in over a long way, so the view never settled).
      onClick={(_event, position) => {
        const zoom = getZoom();
        const { width, height, transform } = store.getState();
        const [tx, ty] = transform ?? [Number.NaN, Number.NaN];
        const distance = Math.hypot(position.x - (width / 2 - tx) / zoom, position.y - (height / 2 - ty) / zoom) * zoom;
        setCenter(position.x, position.y, { zoom, duration: minimapMoveMs(distance, Math.max(width, height)) });
      }}
      nodeColor={minimapColor}
      nodeBorderRadius={4}
      nodeStrokeWidth={0}
      maskColor="color-mix(in srgb, var(--foreground) 8%, transparent)"
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
  const revealTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => () => revealTimers.current.forEach(clearTimeout), []);
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
      let freshIds: string[] = [];
      const reveal = (first: boolean) => {
        const { width, height } = store.getState();
        const all = getNodes();
        if (first) {
          freshIds = all.filter((n) => !before.has(n.id)).map((n) => n.id);
          remember();
        }
        const fresh = all.filter((n) => freshIds.includes(n.id));
        if (fresh.length === 0 || width <= 0 || before.size === 0) return;
        // A small flow that no longer fits (a copy and its "Add step" cards land beside the original): show all of it instead of cutting the original off.
        if (realSteps(all) <= READABLE_STEP_LIMIT && !isInView(getNodesBounds(all), getViewport(), { width, height })) {
          // Everything (the original, its copies and their "Add step" cards) in one view, even if that means a smaller zoom than the usual readable floor.
          const b = getNodesBounds(all);
          const zoom = Math.min(1, Math.max(FIT_MIN_ZOOM_NARROW, Math.min((width - 2 * FIT_SIDE_INSET) / b.width, (height - FIT_TOP_INSET - FIT_BOTTOM_INSET) / b.height)));
          setViewport({ x: (width - b.width * zoom) / 2 - b.x * zoom, y: FIT_TOP_INSET - b.y * zoom, zoom }, { duration: motionMs(260) });
          return;
        }
        // A card that has not been measured yet counts with the usual card size.
        const rects = fresh.map((n) => ({ x: n.position.x, y: n.position.y, width: n.width ?? 236, height: n.height ?? 62 }));
        const left = Math.min(...rects.map((r) => r.x));
        const top = Math.min(...rects.map((r) => r.y));
        const bounds = { x: left, y: top, width: Math.max(...rects.map((r) => r.x + r.width)) - left, height: Math.max(...rects.map((r) => r.y + r.height)) - top };
        const next = panToReveal(bounds, getViewport(), { width, height }, undefined, coveredByOverlays(width, height, nodeCount >= MINIMAP_MIN_STEPS));
        if (next) setViewport({ ...next, zoom: getViewport().zoom }, { duration: motionMs(200) });
      };
      // These timers must outlive a re-render (the effect re-runs whenever the React Flow helpers change identity), so they are not cleared by this effect's cleanup.
      revealTimers.current.forEach(clearTimeout);
      // The side panel for the new copy opens a moment later and narrows the canvas: look again once it has.
      revealTimers.current = [setTimeout(() => reveal(true), 150), setTimeout(() => reveal(false), 700)];
      return;
    }
    const removed = nodeCount < previous.nodeCount || edgeCount < previous.edgeCount;
    if (!removed && layoutRevision === previous.layoutRevision) return;
    // Tidy layout (or its Undo) always re-fits, once the steps have glided to their places; a removal only when something is out of sight.
    const relaid = layoutRevision !== previous.layoutRevision;
    const timer = setTimeout(() => {
      const nodes = getNodes();
      const { width, height } = store.getState();
      if (!relaid && nodes.length > 0 && width > 0 && isInView(getNodesBounds(nodes), getViewport(), { width, height })) return;
      const { width: w, height: h } = store.getState();
      fitClearOfOverlays(rfRef.current, w, h, motionMs(260));
    }, relaid ? motionMs(TIDY_GLIDE_MS) + 40 : 60);
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
  // Several steps picked on purpose (shift-click, a selection box, select all) stay selected while the open step is one of them.
  if (selectedNodeId && nodes.filter((n) => n.selected).length > 1 && nodes.some((n) => n.id === selectedNodeId && n.selected)) return nodes;
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
      if (top < FIT_TOP_INSET - 8) rfRef.current.setViewport({ ...vp, y: vp.y + (FIT_TOP_INSET - top) }, { duration: motionMs(150) });
    }, 80);
    return () => clearTimeout(timer);
  }, [selectedNodeId]);
  return null;
}

/** Marks the run details sheet, which lies over the right part of the canvas while a run is open. */
export const FLOW_RUN_SHEET_ATTR = 'data-flow-run-sheet';

/**
 * While the run details sheet is open it covers the right 44-62% of the canvas, with the step that failed or finished often
 * behind it (final2-04). The flow is fitted again into the part the sheet leaves free. Closing the sheet leaves the view as
 * it is: the whole flow is still on screen, just to the left.
 */
export function KeepRunClearOfSheet({ runOpen }: { runOpen: boolean }) {
  const rf = useReactFlow();
  const rfRef = useRef(rf);
  rfRef.current = rf;
  const store = useStoreApi();
  const width = useStore((s) => s.width);
  const height = useStore((s) => s.height);
  // Not before the steps have been measured: React Flow fits the whole canvas once at the start and that would undo this.
  const ready = useNodesInitialized();
  useEffect(() => {
    if (!runOpen || !ready || !width || !height) return;
    const fit = () => {
      const sheet = document.querySelector<HTMLElement>(`[${FLOW_RUN_SHEET_ATTR}]`);
      const canvas = document.querySelector('.react-flow')?.getBoundingClientRect();
      // The sheet lies against the right edge of the window (its slide-in does not change its layout width).
      const covered = sheet && canvas ? Math.max(0, canvas.right - (window.innerWidth - sheet.offsetWidth)) : 0;
      if (covered > 0 && covered < width - 200) fitClearOfOverlays(rfRef.current, width - covered, height, 150);
    };
    // For the first 2.5 s the flow is fitted again whenever the view moves and then stays still for a moment (the canvas fits
    // itself once when it opens, after this has run). Later the person's own panning is left alone.
    let debounce: ReturnType<typeof setTimeout> | undefined;
    const kick = () => {
      if (debounce) clearTimeout(debounce);
      debounce = setTimeout(fit, 120);
    };
    const first = setTimeout(fit, 150);
    const unsubscribe = store.subscribe((state, prev) => { if (state.transform !== prev.transform) kick(); });
    const stop = setTimeout(() => { unsubscribe(); }, 2500);
    return () => {
      clearTimeout(first);
      clearTimeout(stop);
      if (debounce) clearTimeout(debounce);
      unsubscribe();
    };
  }, [runOpen, ready, width, height, store]);
  return null;
}
