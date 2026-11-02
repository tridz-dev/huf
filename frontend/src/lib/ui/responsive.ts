import { useEffect, useState } from 'react';

/**
 * The one set of screen-width rules for the flow screens (UX-23). Every responsive decision in the editor reads from
 * here so the header, the step panel, the sheets and the app navigation always agree about what "narrow" means.
 *
 *   xl  >= 1440   everything on show
 *   lg  1200-1439
 *   md  1024-1199 (and the app navigation is already the icon rail from 1200 down)
 *   sm  768-1023  touch sizes; the step panel opens over the canvas instead of beside it
 *   xs  < 768     phone
 */
export type Band = 'xl' | 'lg' | 'md' | 'sm' | 'xs';

export const BREAKPOINTS = { xl: 1440, lg: 1200, md: 1024, sm: 768 } as const;

/** At or below this width the app navigation turns into the icon rail by itself. */
export const NAV_COLLAPSE_AT = 1200;
/** Below this width controls are 44px (touch); from it up 32px. */
export const TOUCH_BELOW = 1024;

export function bandForWidth(width: number): Band {
  if (width >= BREAKPOINTS.xl) return 'xl';
  if (width >= BREAKPOINTS.lg) return 'lg';
  if (width >= BREAKPOINTS.md) return 'md';
  if (width >= BREAKPOINTS.sm) return 'sm';
  return 'xs';
}

export interface Viewport {
  width: number;
  band: Band;
  /** Phone: below 768. */
  isPhone: boolean;
  /** 1200 and narrower: header actions fold into the "..." menu, the app navigation is the icon rail. */
  isCompact: boolean;
  /** Below 1024: fingers, so 44px targets. */
  isTouch: boolean;
}

export function viewportFor(width: number): Viewport {
  return {
    width,
    band: bandForWidth(width),
    isPhone: width < BREAKPOINTS.sm,
    isCompact: width <= NAV_COLLAPSE_AT,
    isTouch: width < TOUCH_BELOW,
  };
}

const currentWidth = () => (typeof window === 'undefined' ? 1440 : window.innerWidth);

/** The band the window is in now; re-renders only when a band edge is crossed or the width changes by a resize. */
export function useViewport(): Viewport {
  const [width, setWidth] = useState(currentWidth);
  useEffect(() => {
    let frame = 0;
    const onResize = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setWidth(window.innerWidth));
    };
    window.addEventListener('resize', onResize);
    onResize();
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', onResize);
    };
  }, []);
  return viewportFor(width);
}

/** Step panel: how wide the person may drag it, and how little canvas must stay beside it. */
export const PANEL_MIN = 300;
export const PANEL_MAX = 480;
export const CANVAS_MIN = 520;
/** The icon rail of step types on the canvas's left edge. */
export const NODE_RAIL_WIDTH = 48;
export const PANEL_STORAGE_KEY = 'huf.flow.panelWidth';

/** Width kept for the step panel: what was dragged, else a comfortable default for the window (wider screens get more). */
export function defaultPanelWidth(viewportWidth: number): number {
  return viewportWidth >= BREAKPOINTS.xl ? 360 : viewportWidth >= BREAKPOINTS.md ? 340 : PANEL_MIN;
}

export function clampPanelWidth(width: number): number {
  if (!Number.isFinite(width)) return PANEL_MIN;
  return Math.min(PANEL_MAX, Math.max(PANEL_MIN, Math.round(width)));
}

export function readStoredPanelWidth(): number | null {
  try {
    const raw = window.localStorage.getItem(PANEL_STORAGE_KEY);
    const n = raw === null ? NaN : Number(raw);
    return Number.isFinite(n) ? clampPanelWidth(n) : null;
  } catch {
    return null;
  }
}

export function storePanelWidth(width: number): void {
  try {
    window.localStorage.setItem(PANEL_STORAGE_KEY, String(clampPanelWidth(width)));
  } catch {
    void 0;
  }
}

/**
 * How the step panel is shown in the room the editor has (`available` = the editor's width: everything to the right of the
 * app navigation). Docked beside the canvas as long as the canvas keeps CANVAS_MIN; it is narrowed toward PANEL_MIN first.
 * Below that it opens over the canvas as a sheet (at most 62% of the window).
 */
export function panelLayout(available: number, wanted: number): { mode: 'docked'; width: number } | { mode: 'sheet' } {
  const room = available - NODE_RAIL_WIDTH - CANVAS_MIN;
  if (room < PANEL_MIN) return { mode: 'sheet' };
  return { mode: 'docked', width: Math.min(clampPanelWidth(wanted), Math.min(room, PANEL_MAX)) };
}

/** Widest a sheet may be: 62% of the window (a sheet never hides most of the editor). */
export function sheetMaxWidth(viewportWidth: number): number {
  return Math.round(viewportWidth * 0.62);
}

/** Tap-sized controls: 32px on a desktop window, 44px below 1024 (fingers). Add to icon buttons and menu rows. */
export const HIT_TARGET = 'min-h-8 min-w-8 max-[1023px]:min-h-11 max-[1023px]:min-w-11';
