/**
 * "Tidy layout" and the view helpers around it. The layout itself lives in lib/flow-canvas/autoLayout.ts (layered,
 * branch-aware, even spacing); this file adds the branch order of real flow connections and keeps the old names.
 */
import { autoLayout, CARD_WIDTH, COLUMN_GAP, ROW_GAP, type LayoutEdge, type LayoutNode } from '../flow-canvas/autoLayout';
import { branchHandlesFor } from './flowBranches';

export { CARD_WIDTH, COLUMN_GAP, ROW_GAP };

interface StepLike extends LayoutNode {
  data?: { actionConfig?: object | undefined };
}
interface ConnectionLike extends LayoutEdge {
  sourceHandle?: string | null;
  data?: { route?: string } | undefined;
}

/**
 * New positions keyed by step id. Branches keep their left-to-right order: Yes before No, Approved before Rejected, the
 * loop's body before "When done" (the order of the step's own branch handles), router paths in the order they were added.
 */
export function tidyPositions(nodes: StepLike[], edges: ConnectionLike[]): Record<string, { x: number; y: number }> {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const ordered = edges.map((e, i) => {
    if (e.order !== undefined) return e;
    const cfg = byId.get(e.source)?.data?.actionConfig as ({ type?: string } & Record<string, unknown>) | undefined;
    const handles = branchHandlesFor(cfg?.type, cfg);
    const route = e.data?.route ?? e.sourceHandle ?? 'next';
    const at = handles.findIndex((h) => h.route === route);
    return { ...e, order: (at >= 0 ? at : handles.length) + i / 1000 };
  });
  return autoLayout(nodes, ordered);
}

/**
 * A graph saved without positions (a template, a copy made by a script, a flow written by hand) is laid out the way
 * "Tidy layout" would; one that has them keeps them. Steps stacked on one spot count as having none.
 */
export function layoutWhenUnplaced<T extends StepLike>(nodes: T[], edges: ConnectionLike[], someMissing: boolean): T[] {
  if (nodes.length < 2) return nodes;
  const spots = new Set(nodes.map((n) => `${Math.round(n.position.x / 40)}:${Math.round(n.position.y / 40)}`));
  if (!someMissing && spots.size === nodes.length) return nodes;
  const positions = tidyPositions(nodes, edges);
  return nodes.map((n) => ({ ...n, position: positions[n.id] ?? n.position }));
}

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * The viewport offset that brings `rect` fully into view at the current zoom with `pad` px clear, moving as little as possible
 * (a rect taller or wider than the canvas is aligned to its top-left). Null when it is already fully visible.
 * `covered` is an overlay drawn on the canvas (screen px, canvas origin: the overview and zoom buttons bottom-left): a rect
 * that would sit under it is lifted until it clears the overlay, as long as its top stays in view.
 */
export function panToReveal(
  rect: Box,
  viewport: { x: number; y: number; zoom: number },
  size: { width: number; height: number },
  pad = 24,
  covered?: Box,
): { x: number; y: number } | null {
  const screen = (vp: { x: number; y: number; zoom: number }) => ({
    left: rect.x * vp.zoom + vp.x,
    top: rect.y * vp.zoom + vp.y,
    w: rect.width * vp.zoom,
    h: rect.height * vp.zoom,
  });
  const under = (vp: { x: number; y: number; zoom: number }) => {
    if (!covered) return false;
    const r = screen(vp);
    return r.left < covered.x + covered.width && r.left + r.w > covered.x && r.top < covered.y + covered.height && r.top + r.h > covered.y;
  };
  if (isInView(rect, viewport, size) && !under(viewport)) return null;
  const { left, top, w, h } = screen(viewport);
  const shift = (start: number, len: number, avail: number): number => {
    if (len + 2 * pad > avail || start < pad) return pad - start;
    if (start + len > avail - pad) return avail - pad - (start + len);
    return 0;
  };
  const moved = { ...viewport, x: viewport.x + shift(left, w, size.width), y: viewport.y + shift(top, h, size.height) };
  if (covered && under(moved)) {
    const r = screen(moved);
    const lift = covered.y - pad - (r.top + r.h);
    if (lift < 0 && r.top + lift >= pad) moved.y += lift;
  }
  return { x: moved.x, y: moved.y };
}

/** True when `rect` (flow coordinates) sits fully inside the visible canvas, keeping `margin` px clear (none by default: only content that is actually cut off counts). */
export function isInView(
  rect: Box,
  viewport: { x: number; y: number; zoom: number },
  size: { width: number; height: number },
  margin = { top: 0, side: 0, bottom: 0 },
): boolean {
  const left = rect.x * viewport.zoom + viewport.x;
  const top = rect.y * viewport.zoom + viewport.y;
  const right = left + rect.width * viewport.zoom;
  const bottom = top + rect.height * viewport.zoom;
  return left >= margin.side && top >= margin.top && right <= size.width - margin.side && bottom <= size.height - margin.bottom;
}
