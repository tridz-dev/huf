// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SlackPolicySection, slackSaveFields } from './SlackPolicySection';
import { ConnectionStatus } from './ConnectionStatus';
import type { GatewayDoc } from '@/services/gatewayApi';

const base = {
  name: 'GW', gateway_name: 'G', provider: 'Slack', is_enabled: 1, direct_policy: 'Pairing',
  unmapped_policy: 'Use service user', private_reply_policy: 'Always private', show_feedback_buttons: 0,
} as GatewayDoc;

describe('SlackPolicySection', () => {
  it('renders the three Slack controls and reports changes', () => {
    const onChange = vi.fn();
    render(<SlackPolicySection gateway={base} onChange={onChange} />);
    expect(screen.getByLabelText('When a person is not linked')).toHaveTextContent('Use service user');
    expect(screen.getByLabelText('Where to send answers')).toHaveTextContent('Always private');
    const sw = screen.getByLabelText('Ask for feedback after answers');
    fireEvent.click(sw);
    expect(onChange).toHaveBeenCalledWith({ show_feedback_buttons: 1 });
  });

  it('is hidden for other providers and only saves for Slack', () => {
    const other = { ...base, provider: 'Telegram' } as GatewayDoc;
    const { container } = render(<SlackPolicySection gateway={other} onChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    expect(slackSaveFields(other)).toEqual({});
    expect(slackSaveFields(base)).toEqual({
      unmapped_policy: 'Use service user', private_reply_policy: 'Always private', show_feedback_buttons: 0,
    });
  });
});

describe('ConnectionStatus', () => {
  it('shows state badge, reason and last error', () => {
    render(<ConnectionStatus gateway={{ ...base, connection_state: 'Degraded', connection_reason: 'Token expiring', last_error: 'boom' }} />);
    expect(screen.getByText('Degraded')).toBeInTheDocument();
    expect(screen.getByText('Token expiring')).toBeInTheDocument();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });
});
