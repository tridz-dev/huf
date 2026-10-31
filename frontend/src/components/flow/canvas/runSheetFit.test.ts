// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import type { Node, ReactFlowInstance } from 'reactflow';

vi.mock('reactflow', () => ({
  useNodesInitialized: () => false, useReactFlow: () => ({}), useStoreApi: () => ({}), useStore: () => 0, Controls: () => null, MiniMap: () => null,
  getNodesBounds: (ns: Node[]) => {
    const l = Math.min(...ns.map((n) => n.position.x)), t = Math.min(...ns.map((n) => n.position.y));
    return { x: l, y: t, width: Math.max(...ns.map((n) => n.position.x + (n.width ?? 0))) - l, height: Math.max(...ns.map((n) => n.position.y + (n.height ?? 0))) - t };
  },
}));
import { fitClearOfOverlays } from './canvasView';

const node = (id: string, x: number, y: number, type = 'step'): Node => ({ id, type, position: { x, y }, positionAbsolute: { x, y }, width: 236, height: 100, data: {} });

describe('ux44: the flow fits into the part the run sheet leaves free', () => {
  it('shrinks a two-branch flow to fit a 504 px free area instead of leaving a branch behind the sheet', () => {
    const nodes = [node('t', 215, 0, 'trigger'), node('a', 0, 200), node('b', 430, 200)];
    const setViewport = vi.fn();
    const rf = { getNodes: () => nodes, setViewport } as unknown as ReactFlowInstance;
    fitClearOfOverlays(rf, 504, 800);
    const vp = setViewport.mock.calls[0][0] as { x: number; y: number; zoom: number };
    const right = Math.max(...nodes.map((n) => (n.position.x + 236) * vp.zoom + vp.x));
    const left = Math.min(...nodes.map((n) => n.position.x * vp.zoom + vp.x));
    expect(vp.zoom).toBeGreaterThanOrEqual(0.5);
    expect(left).toBeGreaterThanOrEqual(0);
    expect(right).toBeLessThanOrEqual(504);
  });
});
