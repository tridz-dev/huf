// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FIXTURE_REGISTRY } from '@/lib/flow-gateway/registryFixture';

const last = vi.fn();
const sample = vi.fn();
vi.mock('@/hooks/flow/useGatewayRegistry', () => ({ useGatewayRegistry: () => ({ registry: FIXTURE_REGISTRY, loading: false, failed: false, reload: () => undefined }) }));
vi.mock('@/services/flow/gateway/samplesApi', () => ({ getLastGatewayMessage: (...a: unknown[]) => last(...a), getGatewaySample: (...a: unknown[]) => sample(...a) }));

import { GatewayTest } from './GatewayTest';

describe('GatewayTest', () => {
  beforeEach(() => { last.mockReset(); sample.mockReset(); });
  afterEach(cleanup);

  it('says nothing is sent and has no send button', () => {
    render(<GatewayTest flowId="f" nodeId="t" kind="whatsapp" onResult={vi.fn()} />);
    expect(screen.getByTestId('flow-step-test-gateway-note').textContent).toContain('Nothing is sent');
    expect(screen.queryByRole('button', { name: /send/i })).toBeNull();
    expect(screen.getByTestId('flow-step-test-gateway-last')).toBeTruthy();
    expect(screen.getByTestId('flow-step-test-gateway-sample')).toBeTruthy();
  });

  it('hands the edited sample on as the trigger data', () => {
    const onResult = vi.fn();
    render(<GatewayTest flowId="f" nodeId="t" kind="whatsapp" onResult={onResult} />);
    fireEvent.change(screen.getByTestId('flow-step-test-gateway-field-text'), { target: { value: 'Where is my order?' } });
    fireEvent.click(screen.getByTestId('flow-step-test-gateway-use'));
    expect(onResult.mock.calls[0][0].output).toMatchObject({ text: 'Where is my order?', message: 'Where is my order?' });
  });

  it('uses the last real message from the messages service, or says there is none', async () => {
    const onResult = vi.fn();
    last.mockResolvedValueOnce({ found: true, sample: { text: 'hi', sender_id: '••••3210' }, received_at: null, real: true });
    render(<GatewayTest flowId="f" nodeId="t" kind="telegram" onResult={onResult} />);
    fireEvent.click(screen.getByTestId('flow-step-test-gateway-last'));
    await waitFor(() => expect(onResult).toHaveBeenCalled());
    expect(last).toHaveBeenCalledWith('f', 't');
    last.mockResolvedValueOnce({ found: false, sample: null, real: true });
    fireEvent.click(screen.getByTestId('flow-step-test-gateway-last'));
    await waitFor(() => expect(screen.getByTestId('flow-step-test-trigger-note').textContent).toContain('No message has started this flow'));
  });

  it('folds internal fields under Advanced and still uses them', () => {
    const onResult = vi.fn();
    render(<GatewayTest flowId="f" nodeId="t" kind="whatsapp" onResult={onResult} />);
    expect(screen.getByTestId('flow-step-test-gateway-field-text')).toBeTruthy();
    expect(screen.queryByTestId('flow-step-test-gateway-field-kind')).toBeNull();
    expect(screen.queryByText('Hours since their last message')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-step-test-gateway-advanced-toggle'));
    expect(screen.getByTestId('flow-step-test-gateway-field-kind')).toBeTruthy();
    expect(screen.getByTestId('flow-step-test-gateway-field-hours_since_last_customer_message')).toBeTruthy();
    fireEvent.click(screen.getByTestId('flow-step-test-gateway-use'));
    expect(onResult.mock.calls[0][0].output).toMatchObject({ kind: 'message', hours_since_last_customer_message: 0 });
  });
});
