// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from 'sonner';

import { TeamsSetupGuide } from './TeamsSetupGuide';
import {
  TEAMS_PACKAGE_DECODE_ERROR,
  TEAMS_PERMISSION_NOTES,
  TEAMS_RATE_LIMIT_NOTICE,
  TEAMS_READINESS_UNAVAILABLE,
  TEAMS_REVOKE_DELAY_MS,
  TEAMS_VERIFY_COOLDOWN_MS,
  TEAMS_STEPS,
} from './teamsOnboarding';

const api = vi.hoisted(() => ({ manifest: vi.fn(), verify: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock('./teamsApi', () => ({
  generateTeamsAppManifest: (...a: unknown[]) => api.manifest(...a),
  verifyTeamsConnection: (...a: unknown[]) => api.verify(...a),
}));

beforeEach(() => {
  api.manifest.mockReset();
  api.verify.mockReset();
  vi.mocked(toast.info).mockClear();
});
afterEach(() => vi.useRealTimers());

const OK = { ok: true, message: 'All good', steps: [{ id: 'credentials', label: 'Credentials', ok: true, detail: null }] };
const verifyBtn = () => screen.getByRole('button', { name: /Verify connection|Verifying/ });

describe('TeamsSetupGuide', () => {
  it('shows step states from readiness and the generic webhook URL', () => {
    render(
      <TeamsSetupGuide
        gatewayName="GW 1"
        checks={[
          { id: 'teams-credentials', done: true },
          { id: 'teams-first-message', done: false },
        ]}
      />,
    );
    expect(screen.getAllByLabelText('Done')).toHaveLength(1);
    expect(screen.getAllByLabelText('Not done')).toHaveLength(1);
    const input = screen.getByDisplayValue(/handle_gateway_webhook\?gateway_name=GW%201$/);
    expect(input).toBeTruthy();
    expect((input as HTMLInputElement).value).not.toMatch(/teams_webhook|outgoing/i);
    expect(screen.getAllByText(/Teams test send needs a conversation: message the bot first/).length).toBeGreaterThan(0);
  });

  it('never marks the Azure endpoint step Done, even when the endpoint check is done', () => {
    render(<TeamsSetupGuide gatewayName="GW" checks={[{ id: 'teams-messaging-endpoint', done: true }]} />);
    expect(screen.queryAllByLabelText('Done')).toHaveLength(0);
    expect(screen.getAllByLabelText('Check manually').length).toBe(TEAMS_STEPS.length - 0);
  });

  it('prefers the backend public URL from the readiness hint, falling back to the generic URL', () => {
    const hint = 'Paste https://pub.example.com/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=GW as the Messaging endpoint of your Azure Bot (HTTPS).';
    const { unmount } = render(<TeamsSetupGuide gatewayName="GW" checks={[{ id: 'teams-messaging-endpoint', done: false, hint }]} />);
    expect((screen.getByDisplayValue(/pub\.example\.com/) as HTMLInputElement).value).toMatch(/^https:\/\/pub\.example\.com\/api\/method/);
    unmount();
    render(<TeamsSetupGuide gatewayName="GW" checks={[{ id: 'teams-messaging-endpoint', done: false, hint: 'Paste /api/x as the Messaging endpoint' }]} />);
    expect(screen.getByDisplayValue(/handle_gateway_webhook\?gateway_name=GW$/)).toBeTruthy();
  });

  it('renders the real permission and write-only copy constants (RSC wording)', () => {
    render(<TeamsSetupGuide gatewayName="GW" checks={[]} />);
    for (const n of TEAMS_PERMISSION_NOTES) expect(screen.getByText(n)).toBeTruthy();
    expect(TEAMS_PERMISSION_NOTES.join(' ')).toMatch(/only receives messages that @mention it/);
    expect(TEAMS_STEPS.find((s) => s.id === 'credentials')!.body).toMatch(/write-only/);
    expect(screen.getByText(TEAMS_STEPS[1].body)).toBeTruthy();
  });

  it('shows a note only when readiness is unavailable', () => {
    const { unmount } = render(<TeamsSetupGuide gatewayName="GW" checks={undefined} unavailable />);
    expect(screen.getByText(TEAMS_READINESS_UNAVAILABLE)).toBeTruthy();
    unmount();
    render(<TeamsSetupGuide gatewayName="GW" checks={undefined} />);
    expect(screen.queryByText(TEAMS_READINESS_UNAVAILABLE)).toBeNull();
  });

  it('exposes state icons as images and wraps verify results in a polite live region', () => {
    const { container } = render(<TeamsSetupGuide gatewayName="GW" checks={[]} />);
    expect(screen.getAllByRole('img', { name: 'Check manually' }).length).toBeGreaterThan(0);
    expect(container.querySelector('[aria-live="polite"]')).toBeTruthy();
  });

  it('keeps the previous result on a rate limit and shows an info notice, then cools down', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    api.verify.mockResolvedValueOnce(OK);
    render(<TeamsSetupGuide gatewayName="GW" checks={[]} />);
    fireEvent.click(verifyBtn());
    await screen.findByText('Verified');
    expect((verifyBtn() as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { vi.advanceTimersByTime(TEAMS_VERIFY_COOLDOWN_MS + 10); });
    expect((verifyBtn() as HTMLButtonElement).disabled).toBe(false);

    api.verify.mockRejectedValueOnce(Object.assign(new Error('Verify connection was run moments ago'), { exc_type: 'TooManyRequestsError', httpStatus: 429 }));
    fireEvent.click(verifyBtn());
    await screen.findByText(TEAMS_RATE_LIMIT_NOTICE);
    expect(screen.queryByText('Failed')).toBeNull();
    expect(screen.getByText('Verified')).toBeTruthy();
    expect(screen.getByText('Credentials')).toBeTruthy();
    expect(toast.info).toHaveBeenCalledWith(TEAMS_RATE_LIMIT_NOTICE);
    expect((verifyBtn() as HTMLButtonElement).disabled).toBe(true);
  });

  it('treats a 429 status-only error as a rate limit but other errors as Failed', async () => {
    api.verify.mockRejectedValueOnce({ status: 429 });
    const { unmount } = render(<TeamsSetupGuide gatewayName="GW" checks={[]} />);
    fireEvent.click(verifyBtn());
    await screen.findByText(TEAMS_RATE_LIMIT_NOTICE);
    unmount();
    api.verify.mockRejectedValueOnce(new Error('Server exploded'));
    render(<TeamsSetupGuide gatewayName="GW" checks={[]} />);
    fireEvent.click(verifyBtn());
    await screen.findByText('Failed');
  });

  it('guards verify double-clicks with a ref', async () => {
    let resolve!: (v: unknown) => void;
    api.verify.mockReturnValue(new Promise((r) => { resolve = r; }));
    render(<TeamsSetupGuide gatewayName="GW" checks={[]} />);
    const btn = verifyBtn();
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(api.verify).toHaveBeenCalledTimes(1);
    await act(async () => resolve(OK));
  });

  describe('manifest download', () => {
    const dl = () => screen.getByRole('button', { name: /Download Teams app package/ });
    it('downloads, then revokes the object URL after a delay; double click only fetches once', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const create = vi.fn(() => 'blob:x');
      const revoke = vi.fn();
      Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
      const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
      api.manifest.mockResolvedValue({ filename: 'a.zip', content_base64: btoa('zip'), manifest: {} });
      render(<TeamsSetupGuide gatewayName="GW" checks={[]} />);
      fireEvent.click(dl());
      fireEvent.click(dl());
      await waitFor(() => expect(toast.success).toHaveBeenCalled());
      expect(api.manifest).toHaveBeenCalledTimes(1);
      expect(click).toHaveBeenCalledTimes(1);
      expect(revoke).not.toHaveBeenCalled();
      await act(async () => { vi.advanceTimersByTime(TEAMS_REVOKE_DELAY_MS + 10); });
      expect(revoke).toHaveBeenCalledWith('blob:x');
      click.mockRestore();
    });

    it('shows friendly copy when the base64 payload cannot be decoded', async () => {
      api.manifest.mockResolvedValue({ filename: 'a.zip', content_base64: '%%%not base64%%%', manifest: {} });
      render(<TeamsSetupGuide gatewayName="GW" checks={[]} />);
      fireEvent.click(dl());
      await screen.findByText(TEAMS_PACKAGE_DECODE_ERROR);
    });
  });

  it('renders verify steps as a checklist with details', async () => {
    api.verify.mockResolvedValue({
      ok: false,
      message: 'Token request failed',
      steps: [
        { id: 'credentials', label: 'Credentials', ok: true, detail: null },
        { id: 'token', label: 'Token', ok: false, detail: 'invalid_client (secret redacted)' },
      ],
    });
    render(<TeamsSetupGuide gatewayName="GW-1" checks={[]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Verify connection' }));
    await screen.findByText('invalid_client (secret redacted)');
    expect(api.verify).toHaveBeenCalledWith('GW-1');
    expect(screen.getByText('Failed')).toBeTruthy();
    expect(screen.getByLabelText('passed')).toBeTruthy();
    expect(screen.getByLabelText('failed')).toBeTruthy();
  });

  it('shows the site-config keys when the manifest endpoint rejects', async () => {
    api.manifest.mockRejectedValue(new Error('Set site config key teams_app_terms_url to generate the Teams app package.'));
    render(<TeamsSetupGuide gatewayName="GW-1" checks={[]} />);
    fireEvent.click(screen.getByRole('button', { name: /Download Teams app package/ }));
    await waitFor(() => expect(screen.getByText(/teams_app_terms_url/)).toBeTruthy());
  });
});
