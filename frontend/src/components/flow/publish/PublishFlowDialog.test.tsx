// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/flow/flowIntegrations', async (orig) => ({
  ...(await orig<typeof import('@/lib/flow/flowIntegrations')>()),
  useIntegrationStatus: () => ({ slack: { label: 'Slack', connected: false }, gmail: { label: 'Gmail', connected: true } }),
}));

import { PublishFlowDialog } from './PublishFlowDialog';
import { UnpublishFlowDialog } from './UnpublishFlowDialog';

afterEach(cleanup);

const base = {
  open: true,
  onOpenChange: vi.fn(),
  flowId: 'flow-1',
  flowName: 'Order alert',
  steps: [] as Array<{ data: { label?: string; actionConfig?: unknown } }>,
  problems: [],
  publishing: false,
  onConfirm: vi.fn(),
};

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe('PublishFlowDialog', () => {
  it('summarises a webhook start with the address and a Copy button, then confirms', async () => {
    const onConfirm = vi.fn();
    wrap(<PublishFlowDialog {...base} onConfirm={onConfirm} trigger={{ type: 'webhook' }} />);
    expect(screen.getByRole('heading', { name: 'Publish this flow?' })).toBeInTheDocument();
    expect(screen.getByTestId('flow-publish-summary')).toHaveTextContent('This flow will start when a request hits this address');
    expect(screen.getByDisplayValue(/flow_webhook_clean\?flow_id=flow-1/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument();
    expect(screen.queryByTestId('flow-publish-warnings')).toBeNull();
    await userEvent.click(screen.getByTestId('flow-publish-confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('says when a schedule or a record change starts the flow', () => {
    const { unmount } = wrap(<PublishFlowDialog {...base} trigger={{ type: 'schedule', cron: '0 9 * * *' }} />);
    expect(screen.getByTestId('flow-publish-summary')).toHaveTextContent('This flow will start every day at 09:00');
    unmount();
    wrap(<PublishFlowDialog {...base} trigger={{ type: 'doc-event', doctype: 'ToDo', event: 'after_insert' }} />);
    expect(screen.getByTestId('flow-publish-summary')).toHaveTextContent('when a ToDo is created');
  });

  it('warns about a step whose app is not connected and about unfinished steps', () => {
    wrap(
      <PublishFlowDialog
        {...base}
        trigger={{ type: 'webhook' }}
        steps={[{ data: { label: 'Post to Slack', actionConfig: { type: 'tool-call', tool_id: 'slack_send_message' } } }]}
        problems={[{ title: 'Send email', message: 'Enter who to send it to.' }]}
      />,
    );
    const warnings = screen.getByTestId('flow-publish-warnings');
    expect(warnings).toHaveTextContent('Post to Slack will fail until Slack is connected.');
    expect(screen.getByTestId('flow-publish-connect')).toHaveAttribute('href', expect.stringContaining('slack'));
    expect(warnings).toHaveTextContent('Send email: Enter who to send it to.');
    expect(screen.getByTestId('flow-publish-confirm')).toHaveTextContent('Publish anyway');
  });
});

describe('UnpublishFlowDialog', () => {
  it('explains what turning the flow off does', () => {
    wrap(<UnpublishFlowDialog open onOpenChange={vi.fn()} flowName="Order alert" trigger={{ type: 'webhook' }} busy={false} onConfirm={vi.fn()} />);
    expect(screen.getByText('Unpublish this flow?')).toBeInTheDocument();
    expect(screen.getByText(/Requests to its web address are refused/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing is deleted/)).toBeInTheDocument();
  });
});
