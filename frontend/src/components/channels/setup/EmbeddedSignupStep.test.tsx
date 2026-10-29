// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

const api = vi.hoisted(() => ({ getSignupConfig: vi.fn(), completeSignup: vi.fn() }));
vi.mock('@/services/embeddedSignupApi', () => api);

import { EmbeddedSignupStep, isFacebookOrigin, parseSignupMessage } from './EmbeddedSignupStep';

const flush = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
};
const fbMessage = (origin: string, data: unknown) =>
  act(async () => {
    window.dispatchEvent(new MessageEvent('message', { origin, data }));
    await Promise.resolve();
  });
const FINISH = { type: 'WA_EMBEDDED_SIGNUP', event: 'FINISH', data: { waba_id: '111', phone_number_id: '222', business_id: '333' }, version: '3' };

describe('parseSignupMessage', () => {
  it('accepts facebook origins and parses FINISH (object or JSON string)', () => {
    expect(isFacebookOrigin('https://www.facebook.com')).toBe(true);
    expect(isFacebookOrigin('https://business.facebook.com')).toBe(true);
    const want = { kind: 'finish', data: { waba_id: '111', phone_number_id: '222', business_id: '333' } };
    expect(parseSignupMessage({ origin: 'https://www.facebook.com', data: FINISH })).toEqual(want);
    expect(parseSignupMessage({ origin: 'https://web.facebook.com', data: JSON.stringify(FINISH) })).toEqual(want);
  });
  it('rejects non-facebook origins', () => {
    for (const o of ['https://evil.com', 'https://facebook.com.evil.com', 'http://www.facebook.com', 'https://notfacebook.com'])
      expect(parseSignupMessage({ origin: o, data: FINISH })).toBeNull();
  });
  it('handles cancel, error and unrelated messages', () => {
    const o = 'https://www.facebook.com';
    expect(parseSignupMessage({ origin: o, data: { type: 'WA_EMBEDDED_SIGNUP', event: 'CANCEL', data: {} } })).toEqual({ kind: 'cancel' });
    expect(parseSignupMessage({ origin: o, data: { type: 'WA_EMBEDDED_SIGNUP', event: 'ERROR', data: { error_message: 'x' } } })).toEqual({ kind: 'error', message: 'x' });
    expect(parseSignupMessage({ origin: o, data: { type: 'OTHER' } })).toBeNull();
    expect(parseSignupMessage({ origin: o, data: 'not json' })).toBeNull();
    expect(parseSignupMessage({ origin: o, data: { type: 'WA_EMBEDDED_SIGNUP', event: 'FINISH', data: {} } })?.kind).toBe('error');
  });
});

describe('EmbeddedSignupStep', () => {
  const login = vi.fn();
  const init = vi.fn();
  beforeEach(() => {
    login.mockReset();
    init.mockReset();
    api.completeSignup.mockReset();
    api.getSignupConfig.mockReset();
    (window as unknown as { FB: unknown }).FB = { init, login };
    api.getSignupConfig.mockResolvedValue({ enabled: true, app_id: 'app1', config_id: 'cfg1', graph_version: 'v21.0' });
    api.completeSignup.mockResolvedValue({ gateway: 'GW', setup_stage: 'connected_unverified', webhook_url: 'u', verify_token_hint: 'huf-...abcd', warnings: [] });
  });
  afterEach(() => {
    cleanup();
    delete (window as unknown as { FB?: unknown }).FB;
  });

  it('shows Not configured and a disabled button when signup is off', async () => {
    api.getSignupConfig.mockResolvedValue({ enabled: false, app_id: '', config_id: '', graph_version: 'v21.0' });
    render(<EmbeddedSignupStep onConnected={vi.fn()} />);
    await flush();
    expect(screen.getByRole('button', { name: /connect with facebook/i })).toBeDisabled();
    expect(screen.getByText(/not configured/i)).toBeInTheDocument();
  });

  it('does not load the SDK script before click', async () => {
    delete (window as unknown as { FB?: unknown }).FB;
    render(<EmbeddedSignupStep onConnected={vi.fn()} />);
    await flush();
    expect(document.querySelector('script[src*="connect.facebook.net"]')).toBeNull();
  });

  it('logs in with config_id and completes after code + message', async () => {
    const onConnected = vi.fn();
    render(<EmbeddedSignupStep gatewayName="GW" onConnected={onConnected} />);
    await flush();
    fireEvent.click(screen.getByRole('button', { name: /connect with facebook/i }));
    await flush();
    expect(login).toHaveBeenCalledTimes(1);
    const [cb, opts] = login.mock.calls[0];
    expect(opts).toEqual({
      config_id: 'cfg1',
      response_type: 'code',
      override_default_response_type: true,
      extras: { setup: {}, featureType: '', sessionInfoVersion: '3' },
    });
    // a spoofed message from another origin is ignored
    await fbMessage('https://evil.example', FINISH);
    cb({ authResponse: { code: 'the-code' } });
    await flush();
    expect(api.completeSignup).not.toHaveBeenCalled();
    await fbMessage('https://www.facebook.com', FINISH);
    await flush();
    expect(api.completeSignup).toHaveBeenCalledWith({ code: 'the-code', waba_id: '111', phone_number_id: '222', business_id: '333', gateway_name: 'GW' });
    expect(onConnected).toHaveBeenCalledWith(expect.objectContaining({ gateway: 'GW' }));
  });

  it('works when the message arrives before the code', async () => {
    render(<EmbeddedSignupStep onConnected={vi.fn()} />);
    await flush();
    fireEvent.click(screen.getByRole('button', { name: /connect with facebook/i }));
    await flush();
    await fbMessage('https://business.facebook.com', FINISH);
    expect(api.completeSignup).not.toHaveBeenCalled();
    login.mock.calls[0][0]({ authResponse: { code: 'c2' } });
    await flush();
    expect(api.completeSignup).toHaveBeenCalledTimes(1);
  });

  it('shows the generated PIN once before continuing', async () => {
    api.completeSignup.mockResolvedValue({ gateway: 'GW', setup_stage: 's', webhook_url: 'u', verify_token_hint: 'h', warnings: [], pin: '654321' });
    const onConnected = vi.fn();
    render(<EmbeddedSignupStep onConnected={onConnected} />);
    await flush();
    fireEvent.click(screen.getByRole('button', { name: /connect with facebook/i }));
    await flush();
    login.mock.calls[0][0]({ authResponse: { code: 'c' } });
    await fbMessage('https://www.facebook.com', FINISH);
    await flush();
    expect(onConnected).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));
    expect(onConnected).toHaveBeenCalledTimes(1);
  });

  it('surfaces a server error and a cancelled login quietly', async () => {
    api.completeSignup.mockRejectedValue(new Error('Meta said no'));
    render(<EmbeddedSignupStep onConnected={vi.fn()} />);
    await flush();
    fireEvent.click(screen.getByRole('button', { name: /connect with facebook/i }));
    await flush();
    login.mock.calls[0][0]({ authResponse: null });
    await flush();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByRole('button', { name: /connect with facebook/i })).toBeEnabled();
  });
});
