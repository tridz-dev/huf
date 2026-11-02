// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const node = { id: 'start', type: 'trigger', position: { x: 0, y: 0 }, data: { label: 'Choose a trigger', nodeType: 'trigger', icon: 'x' } };
vi.mock('@/contexts/FlowContext', () => ({
  useFlowContext: () => ({ activeFlow: { id: 'f', name: 'F', nodes: [node], edges: [] }, updateNode: vi.fn(), updateNodeData: vi.fn() }),
}));
vi.mock('@/hooks/flow/useFlowPermissions', () => ({ useFlowPermissions: () => ({ canManage: true }) }));
vi.mock('../../../modals/NodeSelectionModal', () => ({ NodeSelectionModal: () => null }));

import { TriggerConfigForm } from '../TriggerConfigForm';
import { TriggerTypeRow } from '../../frame/TriggerTypeRow';

afterEach(cleanup);

describe('w1cap-01: the side panel of a trigger that is not set up', () => {
  it('has one block and one primary button, in plain words', () => {
    render(
      <>
        <TriggerTypeRow node={node as never} />
        <TriggerConfigForm nodeId="start" />
      </>
    );
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Choose what starts this flow' })).toBeTruthy();
    expect(document.body.textContent).not.toContain('Not set up yet');
    expect(document.body.textContent).not.toMatch(/trigger/i);
  });
});
