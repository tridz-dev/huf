// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const api = vi.hoisted(() => ({ getClickToChat: vi.fn(), getWidgetSnippet: vi.fn() }));
vi.mock('@/services/channelsRulesApi', () => api);

import { WidgetsPanel } from './WidgetsPanel';
import type { PanelProps } from './panels';

const props = { gw: 'GW-1', health: { token_check: { phone: { display: '+1 555 123 4567' } } } } as unknown as PanelProps;

describe('WidgetsPanel', () => {
  it('shows link and snippet, refetches on ref change', async () => {
    api.getClickToChat.mockResolvedValue({ wa_me_url: 'https://wa.me/15551234567', qr_svg: null });
    api.getWidgetSnippet.mockResolvedValue('<script src="x"></script>');
    render(<WidgetsPanel {...props} />);
    await waitFor(() => expect(screen.getByDisplayValue('https://wa.me/15551234567')).toBeInTheDocument());
    expect(screen.getByDisplayValue('<script src="x"></script>')).toBeInTheDocument();
    expect(screen.queryByText(/QR codes are not available/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('QR code').querySelector('svg path')).not.toBeNull();
    expect(screen.getByText('Download SVG')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Ref tag'), { target: { value: 'ad1' } });
    await waitFor(() => expect(api.getClickToChat).toHaveBeenLastCalledWith('GW-1', '', 'ad1', '+1 555 123 4567'));
  });
  it('renders QR and download when svg present', async () => {
    api.getClickToChat.mockResolvedValue({ wa_me_url: 'https://wa.me/1', qr_svg: '<svg></svg>' });
    api.getWidgetSnippet.mockResolvedValue('s');
    render(<WidgetsPanel {...props} />);
    expect(await screen.findByText('Download SVG')).toBeInTheDocument();
  });
});
