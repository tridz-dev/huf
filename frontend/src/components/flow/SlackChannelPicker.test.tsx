// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/flowIntegrations', () => ({
  useIntegrationStatus: () => ({ slack: { label: 'Slack', connected: true } }),
}));
vi.mock('@/services/integrationApi', () => ({
  listSlackChannels: vi.fn().mockResolvedValue({
    status: 'Connected',
    channels: [
      { id: 'C0CCDGTDBHR', name: 'huf-live-test', is_private: true },
      { id: 'C02FQ6B1T', name: 'general', is_private: false },
    ],
  }),
}));

import { SlackChannelPicker } from './SlackChannelPicker';

// cmdk and Radix popovers need these in jsdom.
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};

describe('SlackChannelPicker', () => {
  it('reads the channels on first open, filters by name and hands back the id', async () => {
    const onPick = vi.fn();
    render(<SlackChannelPicker value="" onPick={onPick} />);
    fireEvent.click(screen.getByTestId('flow-field-slack-channel-pick'));
    expect(await screen.findByText('#huf-live-test')).toBeTruthy();
    fireEvent.change(screen.getAllByPlaceholderText('Search channels...').find((e) => e.tagName === 'INPUT') as HTMLElement, { target: { value: 'live' } });
    await waitFor(() => expect(screen.queryByText('#general')).toBeNull());
    fireEvent.click(screen.getByText('#huf-live-test'));
    expect(onPick).toHaveBeenCalledWith('C0CCDGTDBHR');
  });
});
