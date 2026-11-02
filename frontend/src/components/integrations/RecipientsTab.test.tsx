// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useForm } from 'react-hook-form';
import { RecipientsTab } from './RecipientsTab';

function Harness() {
  const form = useForm<any>({
    defaultValues: {
      recipients: [
        { recipient_name: 'A', recipient_id: '1', user: '' },
        { recipient_name: 'B', recipient_id: '2', user: '' },
      ],
    },
  });
  return <RecipientsTab form={form} />;
}

describe('RecipientsTab', () => {
  it('renders each recipient as a FieldRow of 3 Fields plus a FieldAction', () => {
    const { container } = render(<Harness />);
    const rows = container.querySelectorAll('[data-field-row]');
    expect(rows).toHaveLength(2);
    rows.forEach((row) => {
      const cells = Array.from(row.children);
      expect(cells).toHaveLength(4);
      cells.forEach((c) => {
        expect(c.querySelector('[data-field-label]')).not.toBeNull();
        expect(c.querySelector('[data-field-note]')).not.toBeNull();
      });
      expect(cells[3].querySelector('[data-field-label]')?.getAttribute('aria-hidden')).toBe('true');
      expect(cells[3].querySelector('button[aria-label="Remove recipient"]')).not.toBeNull();
    });
  });

  it('has no bare controls directly inside a row', () => {
    const { container } = render(<Harness />);
    container.querySelectorAll('[data-field-row]').forEach((row) => {
      Array.from(row.children).forEach((c) => {
        expect(['INPUT', 'BUTTON', 'SELECT']).not.toContain(c.tagName);
      });
    });
  });

  it('removes a recipient via the trash button', () => {
    const { container } = render(<Harness />);
    fireEvent.click(screen.getAllByLabelText('Remove recipient')[0]);
    expect(container.querySelectorAll('[data-field-row]')).toHaveLength(1);
  });
});

describe('RecipientsTab Slack channels', () => {
  afterEach(() => vi.restoreAllMocks());

  function SlackHarness() {
    const form = useForm<any>({ defaultValues: { recipients: [] } });
    return <RecipientsTab form={form} service="slack" settingId="Slack main" />;
  }

  it('loads the channels when the tab opens (read-only) and lists them with copy and save buttons', async () => {
    const api = await import('@/services/integrationApi');
    const spy = vi.spyOn(api, 'listSlackChannels').mockResolvedValue({
      status: 'Connected',
      channels: [{ id: 'C0123456789', name: 'huf-live-test', is_private: false }],
    });
    render(<SlackHarness />);
    expect(screen.getByTestId('slack-channels-loading')).toBeTruthy();
    expect(await screen.findByTestId('slack-channel-huf-live-test')).toBeTruthy();
    expect(screen.queryByTestId('slack-channels-loading')).toBeNull();
    expect(screen.getByLabelText('Copy ID of #huf-live-test')).toBeTruthy();
    expect(spy).toHaveBeenCalledWith('Slack main');
    fireEvent.click(screen.getByTestId('slack-use-huf-live-test'));
    expect(await screen.findByDisplayValue('#huf-live-test')).toBeTruthy();
    expect(screen.getByDisplayValue('C0123456789')).toBeTruthy();
  });

  it('shows the reason when Slack refuses, with Try again', async () => {
    const api = await import('@/services/integrationApi');
    vi.spyOn(api, 'listSlackChannels').mockResolvedValue({ status: 'Rejected', message: 'Slack needs the groups:read permission', channels: [] });
    render(<SlackHarness />);
    expect((await screen.findByTestId('slack-channels-error')).textContent).toContain('groups:read');
    expect(screen.getByTestId('slack-channels-retry')).toBeTruthy();
  });

  it('never stays on Loading: a failed or slow request ends in an error, and Try again loads the list', async () => {
    const api = await import('@/services/integrationApi');
    const spy = vi
      .spyOn(api, 'listSlackChannels')
      .mockRejectedValueOnce(new Error('Slack is taking too long to answer. Try again in a moment.'))
      .mockResolvedValueOnce({ status: 'Connected', channels: [] });
    render(<SlackHarness />);
    const error = await screen.findByTestId('slack-channels-error');
    expect(error.textContent).toContain('taking too long');
    expect(screen.queryByTestId('slack-channels-loading')).toBeNull();
    fireEvent.click(screen.getByTestId('slack-channels-retry'));
    expect(await screen.findByTestId('slack-channels-empty')).toBeTruthy();
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('offers no channel loader for other services or unsaved integrations', () => {
    function H({ service, settingId }: { service?: string; settingId?: string }) {
      const form = useForm<any>({ defaultValues: { recipients: [] } });
      return <RecipientsTab form={form} service={service} settingId={settingId} />;
    }
    const { rerender } = render(<H service="telegram" settingId="x" />);
    expect(screen.queryByTestId('slack-channels')).toBeNull();
    rerender(<H service="slack" />);
    expect(screen.queryByTestId('slack-channels')).toBeNull();
  });
});
