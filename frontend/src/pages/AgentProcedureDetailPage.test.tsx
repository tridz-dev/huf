// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const api = vi.hoisted(() => ({
  getAgentProcedure: vi.fn(),
  getAgentProcedureVersionHistory: vi.fn(),
}));
vi.mock('@/services/agentProcedureApi', async (orig) => ({
  ...(await orig<object>()),
  ...api,
  getSourceFlowId: () => undefined,
}));
vi.mock('@/contexts/PermissionsContext', () => ({
  usePermissions: () => ({ hufRole: 'Admin' }),
}));

import AgentProcedureDetailPage from './AgentProcedureDetailPage';

function renderWith(doc: Record<string, unknown>) {
  api.getAgentProcedure.mockResolvedValue({ procedure_name: 'Refund flow', name: 'PROC-1', procedure_id: 'p1', ...doc });
  api.getAgentProcedureVersionHistory.mockResolvedValue([]);
  return render(
    <MemoryRouter initialEntries={['/procedures/PROC-1']}>
      <Routes>
        <Route path="/procedures/:procedureId" element={<AgentProcedureDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  api.getAgentProcedure.mockReset();
  api.getAgentProcedureVersionHistory.mockReset();
});
afterEach(cleanup);

describe('AgentProcedureDetailPage header badges', () => {
  it('shows the status once and hides the tier badge when it matches the status', async () => {
    renderWith({ status: 'Active', tier: 'Active' });
    await waitFor(() => expect(screen.getByText('Refund flow')).toBeInTheDocument());
    expect(screen.getAllByText('Active')).toHaveLength(1);
  });

  it('shows the tier badge when it differs from the status', async () => {
    renderWith({ status: 'Active', tier: 'Verified' });
    await waitFor(() => expect(screen.getByText('Refund flow')).toBeInTheDocument());
    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.getAllByText('Active')).toHaveLength(1);
  });

  it('falls back to a single Draft status when both fields are missing', async () => {
    renderWith({});
    await waitFor(() => expect(screen.getByText('Refund flow')).toBeInTheDocument());
    expect(screen.getAllByText('Draft')).toHaveLength(1);
  });
});
