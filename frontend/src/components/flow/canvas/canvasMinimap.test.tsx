// @vitest-environment jsdom
import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const setCenter = vi.fn();
let storeState: { width: number; height: number; transform?: [number, number, number] } = { width: 900, height: 700 };
let reduced = false;
let miniMapProps: { onClick?: (e: unknown, p: { x: number; y: number }) => void } = {};

vi.mock('reactflow', () => ({
  Controls: () => null,
  MiniMap: (props: typeof miniMapProps) => {
    miniMapProps = props;
    return null;
  },
  useNodesInitialized: () => true,
  useReactFlow: () => ({ setCenter, getZoom: () => 1.3 }),
  useStore: (select: (s: { width: number }) => number) => select({ width: 900 }),
  useStoreApi: () => ({ getState: () => storeState }),
  getNodesBounds: () => ({ x: 0, y: 0, width: 0, height: 0 }),
}));

import { FlowMiniMap, minimapMoveMs, shiftClearOfCorner } from './canvasView';

beforeEach(() => {
  setCenter.mockClear();
  storeState = { width: 900, height: 700 };
  reduced = false;
  window.matchMedia = ((q: string) => ({ matches: reduced && q.includes('reduce'), media: q, addEventListener: () => undefined, removeEventListener: () => undefined })) as never;
});

describe('FlowMiniMap', () => {
  it('moves the canvas to the clicked spot at once, keeping the zoom', () => {
    render(<FlowMiniMap stepCount={9} />);
    miniMapProps.onClick?.({}, { x: 120, y: 840 });
    expect(setCenter).toHaveBeenCalledWith(120, 840, { zoom: 1.3, duration: 0 });
  });

  it('glides (about 150ms) for a click within one viewport of the current centre', () => {
    storeState = { width: 900, height: 700, transform: [0, 0, 1] }; // centre at (450, 350)
    render(<FlowMiniMap stepCount={9} />);
    miniMapProps.onClick?.({}, { x: 600, y: 500 });
    expect(setCenter).toHaveBeenCalledWith(600, 500, { zoom: 1.3, duration: 150 });
  });

  it('jumps for a click further than one viewport, and never animates for reduced motion', () => {
    storeState = { width: 900, height: 700, transform: [0, 0, 1] };
    render(<FlowMiniMap stepCount={9} />);
    miniMapProps.onClick?.({}, { x: 450, y: 3000 });
    expect(setCenter).toHaveBeenLastCalledWith(450, 3000, { zoom: 1.3, duration: 0 });
    reduced = true;
    miniMapProps.onClick?.({}, { x: 600, y: 500 });
    expect(setCenter).toHaveBeenLastCalledWith(600, 500, { zoom: 1.3, duration: 0 });
  });
});

describe('minimapMoveMs', () => {
  it('is 150 under one viewport and 0 from there', () => {
    expect(minimapMoveMs(100, 900)).toBe(150);
    expect(minimapMoveMs(900, 900)).toBe(0);
  });
});

describe('shiftClearOfCorner', () => {
  const covered = { x: 0, y: 560, width: 266, height: 150 };
  const n = (id: string, x: number, y: number) => ({ id, position: { x, y }, width: 236, height: 62, data: {} }) as never;
  it('moves the flow right when a step sits under the overview and the flow still fits', () => {
    const vp = shiftClearOfCorner([n('a', 0, 0), n('b', 20, 600)], { x: 0, y: 0, zoom: 1 }, covered, 1000);
    expect(vp.x).toBeGreaterThanOrEqual(266 + 12 - 20);
  });
  it('leaves the view alone when nothing is under it, or the shift would push more than half of the flow past the right edge', () => {
    expect(shiftClearOfCorner([n('a', 400, 600)], { x: 0, y: 0, zoom: 0.75 }, covered, 1000)).toEqual({ x: 0, y: 0, zoom: 0.75 });
    expect(shiftClearOfCorner([n('c', 600, 0), n('b', 20, 600)], { x: 0, y: 0, zoom: 1 }, covered, 800).x).toBeGreaterThan(0);
    expect(shiftClearOfCorner([n('c', 600, 0), n('b', 20, 600)], { x: 0, y: 0, zoom: 1 }, covered, 500).x).toBe(0);
    expect(shiftClearOfCorner([n('a', 100, 0), n('b', 20, 600), n('c', 900, 0)], { x: 0, y: 0, zoom: 1 }, covered, 800).x).toBe(0);
    expect(shiftClearOfCorner([n('a', 100, 0), n('b', 20, 600), n('c', 900, 0)], { x: 0, y: 0, zoom: 1 }, covered, 1100).x).toBeGreaterThan(0);
  });
});
