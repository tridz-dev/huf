// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { IntegrationCard } from './IntegrationCard';
import { ConnectionStatusLine } from './ConnectionStatusLine';
import { integrationHealth } from '@/lib/integrations/health';
import type { IntegrationSettingsDoc } from '@/types/integration.types';

const base: IntegrationSettingsDoc = { name: 'gmail-0013', service: 'gmail', is_active: 1, is_default: 0 };

describe('IntegrationCard', () => {
  it('shows a friendly name and one status, never the auto id or a green dot beside a rejection', () => {
    render(
      <IntegrationCard
        setting={{ ...base, last_test_status: 'Rejected', last_test_message: 'Gmail rejected the saved credentials. Update them below, then test again.' }}
        onOpen={vi.fn()}
        onUseInAgent={vi.fn()}
      />,
    );
    expect(screen.getByTestId('integration-card-title').textContent).toBe('Gmail');
    expect(screen.queryByText('gmail-0013')).toBeNull();
    expect(screen.getAllByTestId('integration-status')).toHaveLength(1);
    expect(screen.getByTestId('integration-status').textContent).toBe('Needs attention');
    expect(screen.queryByText(/^active$/i)).toBeNull();
    expect(screen.getByTestId('integration-card-detail').textContent).toContain('Update them below');
  });

  it('opens the page from Fix this and Use in agent without opening the page', () => {
    const onOpen = vi.fn();
    const onUse = vi.fn();
    render(<IntegrationCard setting={{ ...base, last_test_status: 'Rejected' }} onOpen={onOpen} onUseInAgent={onUse} />);
    fireEvent.click(screen.getByTestId('integration-use-in-agent-gmail-0013'));
    expect(onUse).toHaveBeenCalledTimes(1);
    expect(onOpen).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Fix this'));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});

describe('ConnectionStatusLine', () => {
  it('offers the credentials as a button when nothing is saved', () => {
    const onFix = vi.fn();
    const health = integrationHealth({ ...base, last_test_status: 'Not connected', last_test_message: 'No credentials saved yet. Add the client ID first.' });
    render(<ConnectionStatusLine health={health} testing={false} fixLabel="Add credentials" onFix={onFix} />);
    expect(screen.getByTestId('integration-test-result').textContent).toContain('No credentials saved yet');
    expect(screen.getByTestId('integration-test-result').textContent).not.toMatch(/wrong|Reconnect/);
    fireEvent.click(screen.getByTestId('integration-fix-credentials'));
    expect(onFix).toHaveBeenCalled();
  });

  it('never shows Connected next to a last problem unless the problem is shown as newer', () => {
    const health = integrationHealth({ ...base, service: 'slack', last_test_status: 'Connected', last_error: 'Slack could not find that channel.' });
    render(<ConnectionStatusLine health={health} testing={false} lastProblem="Slack could not find that channel." />);
    expect(screen.getByTestId('integration-status').textContent).toBe('Needs attention');
    expect(screen.getByTestId('integration-last-problem').textContent).toContain('since the last check');
  });
});
