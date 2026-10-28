// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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
  it('loads the channels read-only and lists them with copy-id buttons', async () => {
    const api = await import('@/services/integrationApi');
    const spy = vi.spyOn(api, 'listSlackChannels').mockResolvedValue({
      status: 'Connected',
      channels: [{ id: 'C0123456789', name: 'huf-live-test', is_private: false }],
    });
    function SlackHarness() {
      const form = useForm<any>({ defaultValues: { recipients: [] } });
      return <RecipientsTab form={form} service="slack" settingId="Slack main" />;
    }
    render(<SlackHarness />);
    expect(screen.queryByTestId('slack-channel-list')).toBeNull();
    fireEvent.click(screen.getByTestId('slack-load-channels'));
    expect(await screen.findByTestId('slack-channel-huf-live-test')).toBeTruthy();
    expect(screen.getByLabelText('Copy ID of #huf-live-test')).toBeTruthy();
    expect(spy).toHaveBeenCalledWith('Slack main');
  });

  it('shows the reason when Slack refuses', async () => {
    const api = await import('@/services/integrationApi');
    vi.spyOn(api, 'listSlackChannels').mockResolvedValue({ status: 'Rejected', message: 'Slack needs the groups:read permission', channels: [] });
    function SlackHarness() {
      const form = useForm<any>({ defaultValues: { recipients: [] } });
      return <RecipientsTab form={form} service="slack" settingId="Slack main" />;
    }
    render(<SlackHarness />);
    fireEvent.click(screen.getByTestId('slack-load-channels'));
    expect((await screen.findByTestId('slack-channels-error')).textContent).toContain('groups:read');
  });

  it('offers no channel loader for other services or unsaved integrations', () => {
    function H({ service, settingId }: { service?: string; settingId?: string }) {
      const form = useForm<any>({ defaultValues: { recipients: [] } });
      return <RecipientsTab form={form} service={service} settingId={settingId} />;
    }
    const { rerender } = render(<H service="telegram" settingId="x" />);
    expect(screen.queryByTestId('slack-load-channels')).toBeNull();
    rerender(<H service="slack" />);
    expect(screen.queryByTestId('slack-load-channels')).toBeNull();
  });
});
