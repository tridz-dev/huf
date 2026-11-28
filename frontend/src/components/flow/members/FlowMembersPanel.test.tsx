// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

let canManage = true;
vi.mock('@/hooks/flow/useFlowPermissions', () => ({ useFlowPermissions: () => ({ canManage, canExecuteCode: false }) }));
const list = vi.fn();
const remove = vi.fn();
vi.mock('@/services/flow/steps/flowMembersApi', () => ({ listFlowMembers: (...a: unknown[]) => list(...a), removeFlowMember: (...a: unknown[]) => remove(...a) }));

import { FlowMembersPanel } from './FlowMembersPanel';

const ROWS = [
  { member_key: '****0100', member_ref: 'ref-a', status: 'Waiting', current_node_id: 'w', active_flow_run: 'r1', last_event_at: '2026-11-20 10:00:00' },
  { member_key: '****0101', member_ref: 'ref-b', status: 'Completed', current_node_id: null, active_flow_run: null, last_event_at: null },
];
const show = () => render(<FlowMembersPanel flowId="f" open onOpenChange={() => {}} stepName={(id) => (id === 'w' ? 'Wait a day' : undefined)} />);

beforeEach(() => { canManage = true; list.mockResolvedValue(ROWS); remove.mockResolvedValue({ removed: true }); });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('FlowMembersPanel', () => {
  it('lists people with plain status words and the current step', async () => {
    show();
    expect(await screen.findAllByTestId('flow-member-row')).toHaveLength(2);
    expect(screen.getByText('Waiting')).toBeInTheDocument();
    expect(screen.getByText('Finished')).toBeInTheDocument();
    expect(screen.getByText('Wait a day')).toBeInTheDocument();
  });

  it('says so when no one has gone through the flow', async () => {
    list.mockResolvedValue([]);
    show();
    expect((await screen.findByTestId('flow-members-empty')).textContent).toBe('No one has gone through this flow yet. People appear here once a chat or document starts a run.');
  });

  it('says so when loading fails', async () => {
    list.mockRejectedValue(new Error('x'));
    show();
    expect((await screen.findByTestId('flow-members-error')).textContent).toContain('Could not load the people in this flow. Try again.');
  });

  it('removing asks first, then forgets the person and reloads', async () => {
    show();
    fireEvent.click((await screen.findAllByTestId('flow-member-remove'))[0]);
    expect((await screen.findByTestId('flow-member-remove-dialog')).textContent).toContain('This forgets what the flow saved for ****0100 and cancels their waiting run.');
    fireEvent.click(screen.getByTestId('flow-member-remove-confirm'));
    await waitFor(() => expect(remove).toHaveBeenCalledWith('f', 'ref-a'));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it('without edit access the button is off and never asks', async () => {
    canManage = false;
    show();
    const btn = (await screen.findAllByTestId('flow-member-remove'))[0];
    expect(btn).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(btn);
    expect(screen.queryByTestId('flow-member-remove-dialog')).toBeNull();
  });
});
