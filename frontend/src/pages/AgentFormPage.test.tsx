// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';

const api = vi.hoisted(() => ({
  getAgentSection: vi.fn(),
  updateAgentSection: vi.fn(),
  updateAgentDesktopAccess: vi.fn(),
  createAgent: vi.fn(),
}));

vi.mock('@/services/agentApi', async (orig) => ({
  ...(await orig<typeof import('@/services/agentApi')>()),
  getAgentSection: api.getAgentSection,
  updateAgentSection: api.updateAgentSection,
  getAgentDesktopAccess: vi.fn().mockResolvedValue({}),
  updateAgentDesktopAccess: api.updateAgentDesktopAccess,
  createAgent: api.createAgent,
  duplicateAgent: vi.fn(),
  checkCacheableModels: vi.fn().mockResolvedValue({ supported: true, alternatives: [] }),
}));
vi.mock('@/services/providerApi', () => ({ getProviders: vi.fn().mockResolvedValue([]), getModels: vi.fn().mockResolvedValue([]), createProvider: vi.fn(), createModel: vi.fn() }));
vi.mock('@/services/toolApi', () => ({ getToolTypes: vi.fn().mockResolvedValue([]), getToolFunctionsByName: vi.fn().mockResolvedValue([]), getToolFunction: vi.fn(), updateToolFunction: vi.fn() }));
vi.mock('@/services/skillApi', () => ({ getSkillOptions: vi.fn().mockResolvedValue([]) }));
vi.mock('@/services/agentForm/agentFormApi', async (orig) => ({
  ...(await orig<typeof import('@/services/agentForm/agentFormApi')>()),
  getWorkspaceDefaultModel: vi.fn().mockRejectedValue(new Error('not deployed')),
}));
vi.mock('@/lib/frappe-sdk', () => ({ db: { getDocList: vi.fn().mockResolvedValue([]), getDoc: vi.fn() }, call: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/contexts/PermissionsContext', () => ({ usePermissions: () => ({ hufRole: 'Huf Admin', hasCapability: () => true }) }));
vi.mock('@/components/agent/knowledge/useAttachableSources', () => ({ useAttachableSources: () => ({ sources: [], loading: false }) }));
vi.mock('@/components/agent/try/AgentTryPanel', () => ({ AgentTryPanel: ({ agentName }: { agentName?: string }) => <div data-testid="try-panel">{agentName}</div> }));
vi.mock('@/components/agent/delete/DeleteAgentFlow', () => ({ DeleteAgentFlow: () => null }));

import { AgentFormPage } from './AgentFormPage';

const doc = { name: 'support', modified: '2026-01-01 10:00:00', agent_name: 'support', instructions: 'Be helpful', provider: 'gem', model: 'flash',
  agent_modality: 'Both', prompt_mode: 'Local', disabled: 0, allow_chat: 1, owner: 'a@b.c' };

function mount(path: string, ui: ReactElement = <AgentFormPage />) {
  return render(<RouterProvider router={createMemoryRouter([{ path: '/agents/:id', element: ui }], { initialEntries: [path] })} />);
}

describe('AgentFormPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getAgentSection.mockImplementation(async (_id: string, section: string) => ({ name: 'support', section, modified: doc.modified, values: section === 'general' ? doc : {} }));
    api.updateAgentSection.mockImplementation(async (name: string, section: string) => ({ name, section, modified: '2026-01-01 10:05:00', values: {} }));
  });

  it('shows the one-card create flow for a new agent', () => {
    mount('/agents/new');
    expect(screen.getByRole('button', { name: /create and try it/i })).toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
  });

  it('uses the new tab set and the try panel beside an existing agent', async () => {
    mount('/agents/support');
    expect(await screen.findByRole('tab', { name: 'Setup' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Embed' })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Voice' })).not.toBeInTheDocument();
    expect(screen.getByTestId('try-panel')).toHaveTextContent('support');
  });

  it('autosaves an edited section with the expected revision and then reports saved', async () => {
    mount('/agents/support');
    const box = await screen.findByDisplayValue('Be helpful');
    fireEvent.change(box, { target: { value: 'Be very helpful' } });
    await waitFor(() => expect(screen.getByTestId('autosave-status')).toHaveAttribute('data-state', 'dirty'));
    await waitFor(() => expect(api.updateAgentSection).toHaveBeenCalledTimes(1), { timeout: 4000 });
    const [name, section, payload, expected] = api.updateAgentSection.mock.calls[0];
    expect([name, section, expected]).toEqual(['support', 'general', doc.modified]);
    expect(payload.instructions).toBe('Be very helpful');
    expect(payload).not.toHaveProperty('agent_name');
    await waitFor(() => expect(screen.getByTestId('autosave-status')).toHaveAttribute('data-state', 'saved'));
  });

  it('shows an inline error and does not save when required instructions are cleared', async () => {
    mount('/agents/support');
    const box = await screen.findByDisplayValue('Be helpful');
    fireEvent.change(box, { target: { value: '' } });
    fireEvent.click(await screen.findByRole('button', { name: /save now/i }));
    await waitFor(() => expect(screen.getByTestId('autosave-status')).toHaveAttribute('data-state', 'error'));
    expect(api.updateAgentSection).not.toHaveBeenCalled();
  });
});
