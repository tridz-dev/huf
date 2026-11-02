// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';

import { ConnectChannelAgentModal } from './ConnectChannelAgentModal';

const api = vi.hoisted(() => ({
  connection: vi.fn(),
  connect: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/services/agentApi', () => ({
  getAgents: vi.fn().mockResolvedValue([
    { name: 'A1', agent_name: 'Bakery helper' },
    { name: 'A2', agent_name: 'Support bot' },
  ]),
}));
vi.mock('@/services/gatewayApi', () => ({
  getChannelAgentConnection: (...a: unknown[]) => api.connection(...a),
  connectAgentToChannel: (...a: unknown[]) => api.connect(...a),
}));

beforeEach(() => {
  vi.clearAllMocks();
  api.connection.mockResolvedValue({
    service: 'whatsapp',
    provider: 'WhatsApp',
    gateways: [{ name: 'GW-1', is_enabled: 1, default_target_type: 'Agent', default_agent: 'A1' }],
  });
  api.connect.mockResolvedValue({
    gateway: 'GW-1', created: false, enabled: true, enable_error: '', previous_agent: 'A1', tools_added: 1,
  });
});

function renderModal(onConnected = vi.fn()) {
  render(<ConnectChannelAgentModal open onOpenChange={vi.fn()} integrationName="IS-1" onConnected={onConnected} />);
  return onConnected;
}

describe('ConnectChannelAgentModal', () => {
  it('shows the agent that answers today and preselects it', async () => {
    renderModal();
    expect(await screen.findByText('Bakery helper', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Use in agent' })).toBeDisabled();
  });

  it('connects the chosen agent to the existing gateway', async () => {
    const onConnected = renderModal();
    await screen.findByText('Support bot');
    await userEvent.click(screen.getByText('Support bot'));
    await userEvent.click(screen.getByRole('button', { name: 'Use in agent' }));
    await waitFor(() =>
      expect(api.connect).toHaveBeenCalledWith({ integrationSettings: 'IS-1', agent: 'A2', gatewayName: 'GW-1' }),
    );
    expect(toast.success).toHaveBeenCalledWith('Support bot now answers this channel instead of Bakery helper');
    expect(onConnected).toHaveBeenCalled();
  });

  it('warns when the new gateway could not be turned on', async () => {
    api.connection.mockResolvedValue({ service: 'whatsapp', provider: 'WhatsApp', gateways: [] });
    api.connect.mockResolvedValue({
      gateway: 'WhatsApp - Support bot', created: true, enabled: false,
      enable_error: 'Choose a Run as user', previous_agent: null, tools_added: 1,
    });
    renderModal();
    expect(await screen.findByText(/One is created for you/)).toBeInTheDocument();
    await userEvent.click(screen.getByText('Support bot'));
    await userEvent.click(screen.getByRole('button', { name: 'Use in agent' }));
    await waitFor(() => expect(toast.warning).toHaveBeenCalled());
    expect(api.connect.mock.calls[0][0].gatewayName).toBeUndefined();
  });
});
