// @vitest-environment jsdom
import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const setViewport = vi.fn();
const nodesNow: { id: string; type: string; position: { x: number; y: number }; width: number; height: number }[] = [];
let viewport = { x: 0, y: 0, zoom: 1 };

vi.mock('reactflow', () => ({
  useNodesInitialized: () => false,
  // New function objects on every render, like a React Flow instance that is not memoised.
  useReactFlow: () => ({ getNodes: () => nodesNow, getViewport: () => viewport, setViewport, setCenter: vi.fn(), fitView: vi.fn() }),
  useStoreApi: () => ({ getState: () => ({ width: 800, height: 600 }) }),
  getNodesBounds: (ns: typeof nodesNow) => {
    const l = Math.min(...ns.map((n) => n.position.x)), t = Math.min(...ns.map((n) => n.position.y));
    return { x: l, y: t, width: Math.max(...ns.map((n) => n.position.x + n.width)) - l, height: Math.max(...ns.map((n) => n.position.y + n.height)) - t };
  },
}));

import { FitViewAfterRemovalOrLayout } from './canvasView';

const node = (id: string, x: number, y = 0) => ({ id, type: 'action', position: { x, y }, width: 236, height: 62 });

beforeEach(() => {
  vi.useFakeTimers();
  setViewport.mockClear();
  viewport = { x: 0, y: 0, zoom: 1 };
  nodesNow.length = 0;
  nodesNow.push(node('a', 0), node('b', 300));
  window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => undefined, removeEventListener: () => undefined })) as never;
});
afterEach(() => vi.useRealTimers());

describe('FitViewAfterRemovalOrLayout after a duplicate', () => {
  it('brings a copy that landed off screen into view even when the canvas re-renders meanwhile', () => {
    const { rerender } = render(<FitViewAfterRemovalOrLayout flowId="f" nodeCount={2} edgeCount={1} layoutRevision={0} />);
    vi.advanceTimersByTime(500); // settles the known ids
    nodesNow.push(node('copy', 1400));
    rerender(<FitViewAfterRemovalOrLayout flowId="f" nodeCount={3} edgeCount={1} layoutRevision={0} />);
    vi.advanceTimersByTime(50);
    rerender(<FitViewAfterRemovalOrLayout flowId="f" nodeCount={3} edgeCount={1} layoutRevision={0} />); // an unrelated re-render must not cancel the reveal
    vi.advanceTimersByTime(1000);
    expect(setViewport).toHaveBeenCalled();
  });
});
