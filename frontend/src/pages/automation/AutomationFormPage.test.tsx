// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';
import { AutomationFormPage } from './AutomationFormPage';

const createAutomation = vi.fn(async () => ({ name: 'AUT 7/1', status: 'Draft' }));
vi.mock('@/services/automationApi', () => ({
  createAutomation: (...a: unknown[]) => createAutomation(...(a as [])),
  listEventAliases: async () => [],
  getAutomation: vi.fn(),
  listTriggers: vi.fn(),
  createTrigger: vi.fn(),
  updateTrigger: vi.fn(),
  deleteTrigger: vi.fn(),
  updateAutomation: vi.fn(),
  pauseAutomation: vi.fn(),
  resumeAutomation: vi.fn(),
  archiveAutomation: vi.fn(),
}));
vi.mock('@/services/agentApi', () => ({
  getAgents: async () => [],
  getAIModels: async () => [],
  getDocTypes: async () => [],
}));
vi.mock('@/services/projectApi', () => ({ listProjects: async () => [] }));
vi.mock('@/lib/frappe-sdk', () => ({ db: { getDocList: async () => [] } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function Landed() {
  const { name } = useParams();
  return <div>landed:{name}</div>;
}

describe('AutomationFormPage create redirect', () => {
  it('opens the new automation after create', async () => {
    render(
      <MemoryRouter initialEntries={['/automations/new?agent=helper']}>
        <Routes>
          <Route path="/automations/new" element={<AutomationFormPage />} />
          <Route path="/automations/:name" element={<Landed />} />
        </Routes>
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByPlaceholderText('e.g. Weekly usage digest'), 'Digest');
    await userEvent.click(screen.getByRole('tab', { name: 'Task' }));
    await userEvent.type(
      screen.getByPlaceholderText('What should the agent do when this automation runs?'),
      'Summarise',
    );
    await userEvent.click(screen.getByRole('button', { name: /Create automation/ }));
    expect(await screen.findByText('landed:AUT 7/1')).toBeTruthy();
  });
});
