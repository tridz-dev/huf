// @vitest-environment jsdom
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const setCenter = vi.fn();
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
  useStoreApi: () => ({ getState: () => ({ width: 900, height: 700 }) }),
  getNodesBounds: () => ({ x: 0, y: 0, width: 0, height: 0 }),
}));

import { FlowMiniMap } from './canvasView';

describe('FlowMiniMap', () => {
  it('moves the canvas to the clicked spot at once, keeping the zoom', () => {
    render(<FlowMiniMap stepCount={9} />);
    miniMapProps.onClick?.({}, { x: 120, y: 840 });
    expect(setCenter).toHaveBeenCalledWith(120, 840, { zoom: 1.3, duration: 0 });
  });
});
