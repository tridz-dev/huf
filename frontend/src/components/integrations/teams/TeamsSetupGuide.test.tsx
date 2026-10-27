// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { TeamsSetupGuide } from './TeamsSetupGuide';

const api = vi.hoisted(() => ({ manifest: vi.fn(), verify: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('./teamsApi', () => ({
  generateTeamsAppManifest: (...a: unknown[]) => api.manifest(...a),
  verifyTeamsConnection: (...a: unknown[]) => api.verify(...a),
}));

beforeEach(() => {
  api.manifest.mockReset();
  api.verify.mockReset();
});

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
    expect(screen.getByText(/Teams test send needs a conversation: message the bot first/)).toBeTruthy();
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
