// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const save = vi.hoisted(() => vi.fn().mockResolvedValue({}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/gateways/teamsApi', () => ({
  saveTeamsBotSettings: save,
  errorText: (_e: unknown, f: string) => f,
}));

import { TeamsBotSettings } from './TeamsBotSettings';

describe('TeamsBotSettings', () => {
  it('shows loaded values and saves edited ones', async () => {
    render(
      <TeamsBotSettings
        gateway="GW"
        settings={{ allowed_tenants: '', allowed_tenant_list: [], bot_handle: 'Huf', private_output_policy: 'Channel', help_text_override: 'hi' }}
      />,
    );
    expect(screen.getByLabelText('Bot name')).toHaveValue('Huf');
    expect(screen.getByLabelText('Where to send answers')).toHaveTextContent('Reply in the channel');
    fireEvent.change(screen.getByLabelText('Help text'), { target: { value: ' new help ' } });
    fireEvent.click(screen.getByRole('button', { name: /save bot settings/i }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith('GW', { bot_handle: 'Huf', private_output_policy: 'Channel', help_text_override: ' new help ' }),
    );
  });
});
