// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/services/externalAgentsApi', () => ({
  listExternalConnections: vi.fn(() => Promise.resolve([])),
  listExternalSessions: vi.fn(() => Promise.resolve([])),
  listPendingExternalApprovals: vi.fn(() => Promise.resolve([])),
  decideExternalApproval: vi.fn(() => Promise.resolve()),
  listConnectableAgents: vi.fn(() => Promise.resolve([])),
  createExternalConnection: vi.fn(() => Promise.resolve('')),
  updateExternalConnection: vi.fn(() => Promise.resolve()),
  setAgentExecutionMode: vi.fn(() => Promise.resolve()),
  getExternalSessionEvents: vi.fn(() => Promise.resolve([])),
  postExternalUserMessage: vi.fn(() => Promise.resolve({})),
  cancelExternalSession: vi.fn(() => Promise.resolve({})),
}));

import { ExternalAgentsPanel } from './ExternalAgentsPanel';

describe('ExternalAgentsPanel', () => {
  it('shows the connected agents and agent sessions sections, and an empty approvals message', async () => {
    render(<ExternalAgentsPanel />);
    // ApprovalsSection only renders its "Approvals" heading when requests are pending.
    expect(await screen.findByText('Nothing waiting for your approval.')).toBeTruthy();
    expect(await screen.findByRole('heading', { name: 'Connected agents' })).toBeTruthy();
    expect(await screen.findByRole('heading', { name: 'Agent sessions' })).toBeTruthy();
  });
});
