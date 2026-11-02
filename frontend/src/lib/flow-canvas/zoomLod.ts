/**
 * Semantic zoom for the flow canvas (UX_DESIGN_DECISIONS (f)). Pure functions, no React, so the thresholds are unit tested.
 *
 * What a step card shows depends on how big it is on screen:
 *   80% and up   `full`     icon, title, one subtitle line, status word
 *   50% to 80%   `compact`  icon, title (counter-scaled so it stays readable) and a status dot
 *   under 50%    `icon`     an icon tile; the title (12px) shows on hover or focus
 * Labels drawn over the canvas (branch names, line buttons) are counter-scaled so they are 12px on screen at every zoom.
 */

export type CardLod = 'full' | 'compact' | 'icon';

/** The canvas zooms between these two (React Flow `minZoom` / `maxZoom`). */
export const ZOOM_MIN = 0.25;
export const ZOOM_MAX = 1.5;

/** From this zoom up a card shows everything. */
export const LOD_FULL_MIN = 0.8;
/** From this zoom up (and under LOD_FULL_MIN) a card shows icon, title and a status dot. */
export const LOD_COMPACT_MIN = 0.5;

/** On-screen size (px) of the branch names and other labels drawn over the canvas, at every zoom. */
export const LABEL_PX = 12;

export function lodForZoom(zoom: number): CardLod {
  if (zoom >= LOD_FULL_MIN) return 'full';
  if (zoom >= LOD_COMPACT_MIN) return 'compact';
  return 'icon';
}

/**
 * Scale that makes something drawn inside the zoomed canvas come out the same size on screen as at 100%.
 * Capped so a label never grows past a few hundred px of canvas at the smallest zoom.
 */
export function counterScale(zoom: number, max = 1 / ZOOM_MIN): number {
  if (!(zoom > 0)) return 1;
  return Math.min(1 / zoom, max);
}

/** Steps of 5% the cards care about: a card re-renders when this changes, not on every wheel tick. */
const KEY_STEPS_PER_UNIT = 20;

/** A coarse, stable stand-in for the zoom: 20 for the whole full range, then one value per 5%. */
export function zoomKey(zoom: number): number {
  if (zoom >= LOD_FULL_MIN) return KEY_STEPS_PER_UNIT;
  return Math.max(Math.floor(zoom * KEY_STEPS_PER_UNIT + 1e-9), 1);
}

export const lodForKey = (key: number): CardLod => lodForZoom(key / KEY_STEPS_PER_UNIT + 1e-9);
export const zoomOfKey = (key: number): number => Math.max(key / KEY_STEPS_PER_UNIT, ZOOM_MIN);

/** Largest factor a compact card's content is enlarged by (so a title stays readable without outgrowing the card). */
const COMPACT_MAX_GROWTH = 1.7;
/** Share of full size the compact content is drawn at on screen (14px title -> about 13px). */
const COMPACT_TARGET = 0.95;

/** How much to enlarge the content of a compact card (1 = the normal size) at this zoom. */
export function compactGrowth(zoom: number): number {
  if (!(zoom > 0)) return 1;
  return Math.min(Math.max(COMPACT_TARGET / zoom, 1), COMPACT_MAX_GROWTH);
}

/** Size (flow px) of the icon inside an icon tile: about 26px on screen, never more than 64px of canvas. */
export function tileIconSize(zoom: number): number {
  if (!(zoom > 0)) return 28;
  return Math.round(Math.min(Math.max(26 / zoom, 28), 64));
}

/** Font size (flow px) of the hover title of an icon tile: LABEL_PX on screen. */
export function hoverTitlePx(zoom: number): number {
  return Math.round(LABEL_PX * counterScale(zoom) * 10) / 10;
}

/** The view to start from for a flow of `steps` steps: never under 75% up to 15 steps; bigger flows may fit smaller. */
export const READABLE_STEP_LIMIT = 15;
export const FIT_MIN_READABLE = 0.75;
