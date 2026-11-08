// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/services/externalAgentsApi', () => ({
  getApprovals: vi.fn(() => Promise.resolve([])),
  getConnections: vi.fn(() => Promise.resolve([])),
  getSessions: vi.fn(() => Promise.resolve([])),
}));

import { ExternalAgentsPanel } from './ExternalAgentsPanel';

describe('ExternalAgentsPanel', () => {
  it('shows the approvals, connected agents and agent sessions sections', async () => {
    render(<ExternalAgentsPanel />);
    expect(await screen.findByRole('heading', { name: 'Approvals' })).toBeTruthy();
    expect(await screen.findByRole('heading', { name: 'Connected agents' })).toBeTruthy();
    expect(await screen.findByRole('heading', { name: 'Agent sessions' })).toBeTruthy();
  });
});
