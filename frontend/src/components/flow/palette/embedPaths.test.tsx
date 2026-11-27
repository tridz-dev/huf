// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, renderHook, screen } from '@testing-library/react';
import { setAppNodeTypes } from '@/lib/flow-graph/appNodeTypes';
import { writeClipboard, buildClipboard } from '@/lib/flow-history/flowClipboard';
import { setEmbedApp, setScopeTypes } from './embedScope';
import { StepFrame } from '../frame/StepFrame';
import { useFlowStepActions } from '../shortcuts/useFlowStepActions';

const step = { id: 's', type: 'action', position: { x: 0, y: 0 }, data: { label: 'Old step', nodeType: 'action', actionConfig: { type: 'tool-call', tool_id: 'http_request' } } } as never;
const updateNodesAndEdges = vi.fn();

vi.mock('@/contexts/FlowContext', () => ({
  useFlowContext: () => ({ getFlow: () => ({ id: 'f', nodes: [step], edges: [] }), updateNodesAndEdges, setSelectedNode: vi.fn(), undo: vi.fn(), activeFlowId: 'f' }),
}));

const scoped = () => {
  setEmbedApp('happiol');
  setScopeTypes(['condition']);
  setAppNodeTypes([]);
};

afterEach(() => {
  cleanup();
  setEmbedApp(null);
  setAppNodeTypes(null);
  localStorage.clear();
});

describe('embedded editor, out-of-scope step', () => {
  it('opens read-only: no fields', () => {
    scoped();
    render(<StepFrame node={step} onDelete={() => {}} />);
    expect(screen.getByRole('status').textContent).toContain('This step cannot be edited here');
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('cannot be duplicated or pasted', () => {
    scoped();
    writeClipboard(buildClipboard({ nodes: [step], edges: [] }, ['s'], 'f', 1)!);
    const { result } = renderHook(() => useFlowStepActions());
    expect(result.current.duplicate(['s'])).toBe(false);
    expect(result.current.paste()).toBe(false);
    expect(updateNodesAndEdges).not.toHaveBeenCalled();
  });
});
