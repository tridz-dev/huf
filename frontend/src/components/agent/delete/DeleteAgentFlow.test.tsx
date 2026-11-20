// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DeleteAgentFlow } from './DeleteAgentFlow';

const m = vi.hoisted(() => ({ pre: vi.fn(), arch: vi.fn(), del: vi.fn() }));
vi.mock('@/services/agentForm/agentFormApi', () => ({
  getAgentDeletePrecheck: m.pre, archiveAgent: m.arch, deleteAgentCascade: m.del,
}));

const base = { agent: 'A', disabled: false, can_delete: true, can_archive: true, archive_method: '', delete_method: '' };

describe('DeleteAgentFlow', () => {
  it('lists dependents, says automations, offers Disable instead', async () => {
    m.pre.mockResolvedValue({ ...base, counts: { conversations: 3, runs: 5, automations: 0, triggers: 2 }, has_linked: true, suggest_archive: true });
    const onDone = vi.fn();
    render(<DeleteAgentFlow open onOpenChange={() => {}} agentName="A" onDone={onDone} />);
    const deps = await screen.findByTestId('dependents');
    expect(deps).toHaveTextContent('3 conversations');
    expect(deps).toHaveTextContent('2 automations');
    expect(deps).not.toHaveTextContent(/trigger/i);
    await userEvent.click(screen.getByRole('button', { name: 'Disable instead' }));
    expect(m.arch).toHaveBeenCalledWith('A');
  });
  it('without delete permission only offers disable', async () => {
    m.pre.mockResolvedValue({ ...base, can_delete: false, counts: { conversations: 0, runs: 0, automations: 0, triggers: 0 }, has_linked: false, suggest_archive: false });
    render(<DeleteAgentFlow open onOpenChange={() => {}} agentName="A" onDone={() => {}} />);
    expect(await screen.findByRole('button', { name: 'Disable' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
  });
});
