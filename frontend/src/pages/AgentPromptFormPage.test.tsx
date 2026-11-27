// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  getAgentPrompt: vi.fn(),
  createAgentPrompt: vi.fn(),
  updateAgentPrompt: vi.fn(),
  savePrompt: vi.fn(),
}));

vi.mock('@/hooks/permissions/useResourceAccess', () => ({
  useResourceAccess: () => ({ canDelete: true }),
}));
vi.mock('@/services/agentPromptApi', () => ({
  getAgentPrompt: api.getAgentPrompt,
  createAgentPrompt: api.createAgentPrompt,
  updateAgentPrompt: api.updateAgentPrompt,
  createAgentPromptNewVersion: vi.fn(),
  deleteAgentPrompt: vi.fn(),
  forkAgentPrompt: vi.fn(),
  getAgentPromptUsageCount: vi.fn(() => Promise.resolve(0)),
  getAgentsUsingPrompt: vi.fn(() => Promise.resolve([])),
}));
vi.mock('@/components/prompts/promptSave', async (importActual) => ({
  ...(await importActual<typeof import('@/components/prompts/promptSave')>()),
  savePrompt: api.savePrompt,
}));
vi.mock('@/services/categoryApi', () => ({ getCategories: vi.fn(() => Promise.resolve([])) }));
vi.mock('@/components/category/CategoryTab', () => ({ CategoryTab: () => null }));
vi.mock('@/components/category/CategoryModal', () => ({ CategoryModal: () => null }));
vi.mock('@/components/agent/AgentPromptNewVersionDialog', () => ({ AgentPromptNewVersionDialog: () => null }));
vi.mock('@/components/agent/InstructionsTextarea', () => ({
  InstructionsTextarea: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <textarea aria-label="Prompt body" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

import { AgentPromptFormPage } from './AgentPromptFormPage';

const doc = (over: Record<string, unknown> = {}) => ({
  name: 'P1',
  title: 'Greeter',
  slug: 'greeter',
  prompt_body: 'Hello',
  is_active: 1,
  visibility: 'Private',
  version: 1,
  is_latest: 1,
  ...over,
});

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/prompts/:id" element={<><AgentPromptFormPage /><Where /></>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('AgentPromptFormPage', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
    Object.values(api).forEach((fn) => fn.mockReset());
    api.getAgentPrompt.mockResolvedValue(doc());
  });
  afterEach(cleanup);

  it('asks for Title and body, with the other fields under Advanced settings and no second title input', async () => {
    renderAt('/prompts/new');
    expect(await screen.findByLabelText('Prompt body')).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText('e.g. Customer support greeting')).toHaveLength(1);
    expect(screen.queryByLabelText('Slug')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Description')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Tags')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Advanced settings'));
    expect(screen.getByLabelText('Slug')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
    expect(screen.getByLabelText('Tags')).toBeInTheDocument();
    expect(screen.getByText('Visibility')).toBeInTheDocument();
    expect(screen.getByTestId('prompt-advanced-fields')).toHaveTextContent('Active');
  });

  it('saves a changed body through the versioning endpoint and opens the new version', async () => {
    api.getAgentPrompt.mockResolvedValueOnce(doc()).mockResolvedValueOnce(doc({ name: 'P2', version: 2, prompt_body: 'Hello there', previous_version: 'P1' }));
    api.savePrompt.mockResolvedValue({ name: 'P2', version: 2, versioned: true, changed: true });
    renderAt('/prompts/P1');
    const body = await screen.findByLabelText('Prompt body');
    fireEvent.change(body, { target: { value: 'Hello there' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/ }));

    await waitFor(() => expect(api.savePrompt).toHaveBeenCalledTimes(1));
    expect(api.savePrompt.mock.calls[0][0]).toBe('P1');
    expect(api.savePrompt.mock.calls[0][1]).toMatchObject({ prompt_body: 'Hello there', title: 'Greeter' });
    expect(api.updateAgentPrompt).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/prompts/P2'));
  });

  it('stays on the same prompt after a metadata-only save', async () => {
    api.savePrompt.mockResolvedValue({ name: 'P1', version: 1, versioned: false, changed: true });
    renderAt('/prompts/P1');
    await screen.findByLabelText('Prompt body');
    fireEvent.click(screen.getByRole('button', { name: /Save/ }));
    await waitFor(() => expect(api.savePrompt).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getAgentPrompt).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId('where')).toHaveTextContent('/prompts/P1');
  });

  it('cannot save an older version', async () => {
    api.getAgentPrompt.mockResolvedValue(doc({ is_latest: 0 }));
    renderAt('/prompts/P1');
    expect(await screen.findByTestId('prompt-readonly-note')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save/ })).toBeDisabled();
  });
});
