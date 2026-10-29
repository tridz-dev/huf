// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CodeFlowStatus } from '@/services/flow/codeFlowApi';

const status: { value: Partial<CodeFlowStatus> } = { value: {} };
vi.mock('@/lib/flow-graph/useCodeFlowStatus', () => ({
  loadCodeFlowStatus: () => Promise.resolve(status.value),
  refreshCodeFlowStatus: () => Promise.resolve(status.value),
  useCodeFlowStatus: () => ({ status: status.value, loading: false }),
}));
vi.mock('@/services/agentSettingsApi', () => ({
  getAgentSettings: vi.fn(() => Promise.resolve({ name: 'Agent Settings', skill_destinations: JSON.stringify({ mine: { repo_url: 'https://github.com/a/b' } }) })),
  updateAgentSettings: vi.fn(),
}));
vi.mock('@/services/skillApi', () => ({
  getSkillDestinations: vi.fn(() => Promise.resolve([{ name: 'huf-skills', repo_url: 'https://github.com/tridz-dev/huf-skills', path: 'skills', ref: 'main' }])),
}));
vi.mock('@/layouts/PageFrame', () => ({ PageFrame: ({ title, children }: { title: string; children: React.ReactNode }) => <div><h1>{title}</h1>{children}</div> }));

import { AgentSettingsPage } from './AgentSettingsPage';

describe('AgentSettingsPage (Code and skills)', () => {
  beforeEach(() => {
    status.value = {};
  });

  it('is titled for what it contains and says things in plain sentences, for an administrator', async () => {
    status.value = { can_manage: true, allowed: false, server_switch: true } as CodeFlowStatus;
    render(<AgentSettingsPage />);
    expect(await screen.findByRole('heading', { name: 'Code and skills' })).toBeTruthy();
    expect(screen.getByTestId('settings-code-in-flows-status').textContent).toBe('Your server administrator allows code to run on this site.');
    expect(screen.queryByText(/Server switch/)).toBeNull();
    expect(screen.queryByText('Destinations JSON')).toBeNull();
    // friendly list, not a raw JSON box
    expect(screen.getByTestId('skill-source-row-0')).toBeTruthy();
    expect(screen.getByTestId('skill-source-row-1')).toBeTruthy();
    expect(screen.queryByTestId('skill-sources-json')).toBeNull();
    expect(screen.getByTestId('settings-skill-sources-save')).toBeTruthy();
  });

  it('is read-only for people who cannot change it: disabled switch, plain list, no editor and no Save', async () => {
    status.value = { can_manage: false, allowed: true, server_switch: true } as CodeFlowStatus;
    render(<AgentSettingsPage />);
    expect(await screen.findByTestId('settings-code-in-flows-note')).toBeTruthy();
    expect((screen.getByTestId('settings-code-in-flows-switch') as HTMLButtonElement).disabled).toBe(true);
    await waitFor(() => expect(screen.getByTestId('settings-skill-source-huf-skills')).toBeTruthy());
    expect(screen.queryByTestId('skill-sources-editor')).toBeNull();
    expect(screen.queryByTestId('settings-skill-sources-save')).toBeNull();
    expect(screen.queryByTestId('skill-sources-json-toggle')).toBeNull();
  });

  it('says plainly when the server does not allow code', async () => {
    status.value = { can_manage: true, allowed: false, server_switch: false } as CodeFlowStatus;
    render(<AgentSettingsPage />);
    expect((await screen.findByTestId('settings-code-in-flows-status')).textContent).toMatch(/Ask your server administrator/);
  });
});
