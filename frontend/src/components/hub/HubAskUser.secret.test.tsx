// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/services/channels/secretsApi', () => ({ stashSecret: vi.fn() }));
import { stashSecret } from '@/services/channels/secretsApi';
import { HubAskUser, type AskUserPayload } from './HubAskUser';

const stash = vi.mocked(stashSecret);

const ACCESS_TOKEN = 'EAAG-typed-token-123';
const APP_SECRET = 'appsecret-typed-456';

const payload: AskUserPayload = {
  question: 'Enter your Meta app credentials',
  kind: 'secret',
  purpose: 'Connect the WhatsApp gateway',
  allow_free_text: false,
  fields: [
    { id: 'access_token', label: 'Access token', secret: true },
    { id: 'app_secret', label: 'App secret', secret: true },
  ],
};

function renderCard(onSubmit = vi.fn()) {
  render(<HubAskUser payload={payload} onSubmit={onSubmit} />);
  return { onSubmit };
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Access token'), ACCESS_TOKEN);
  await user.type(screen.getByLabelText('App secret'), APP_SECRET);
  await user.click(screen.getByRole('button', { name: 'Submit' }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('HubAskUser secret kind', () => {
  it('renders each field as a masked input with autocomplete off', () => {
    renderCard();
    const token = screen.getByLabelText('Access token');
    const secret = screen.getByLabelText('App secret');
    expect(token).toHaveAttribute('type', 'password');
    expect(secret).toHaveAttribute('type', 'password');
    expect(token).toHaveAttribute('autocomplete', 'off');
    expect(secret).toHaveAttribute('autocomplete', 'off');
    expect(screen.getByText('Connect the WhatsApp gateway')).toBeInTheDocument();
  });

  it('stashes the typed values and sends only the credentials reference to chat', async () => {
    stash.mockResolvedValue({ ok: true, credentials_ref: 'SS-0001', fields: ['access_token', 'app_secret'] });
    const user = userEvent.setup();
    const { onSubmit } = renderCard();

    await fillAndSubmit(user);

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(stash).toHaveBeenCalledTimes(1);
    expect(stash).toHaveBeenCalledWith(
      { access_token: ACCESS_TOKEN, app_secret: APP_SECRET },
      'Connect the WhatsApp gateway',
    );

    const sent = onSubmit.mock.calls[0][0] as string;
    expect(sent).toBe('[secret provided: credentials_ref=SS-0001, fields=access_token,app_secret]');
    expect(sent).not.toContain(ACCESS_TOKEN);
    expect(sent).not.toContain(APP_SECRET);
  });

  it('keeps secret values out of the rendered card after submit', async () => {
    stash.mockResolvedValue({ ok: true, credentials_ref: 'SS-0002', fields: ['access_token', 'app_secret'] });
    const user = userEvent.setup();
    const { onSubmit } = renderCard();

    await fillAndSubmit(user);

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(document.body.textContent).not.toContain(ACCESS_TOKEN);
    expect(document.body.textContent).not.toContain(APP_SECRET);
    expect(screen.queryByLabelText('Access token')).not.toBeInTheDocument();
  });

  it('keeps Submit disabled until every field has a value', async () => {
    const user = userEvent.setup();
    renderCard();
    const submit = screen.getByRole('button', { name: 'Submit' });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText('Access token'), 'x');
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText('App secret'), 'y');
    expect(submit).toBeEnabled();
  });

  it('shows an inline error and sends nothing when the stash fails', async () => {
    stash.mockResolvedValue({ ok: false, message: 'Could not store the credentials.' });
    const user = userEvent.setup();
    const { onSubmit } = renderCard();

    await fillAndSubmit(user);

    expect(await screen.findByText('Could not store the credentials.')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Access token')).toHaveValue('');
    expect(screen.getByLabelText('App secret')).toHaveValue('');
  });

  it('treats a thrown stash call as an inline error and sends nothing', async () => {
    stash.mockRejectedValue(new Error('network down'));
    const user = userEvent.setup();
    const { onSubmit } = renderCard();

    await fillAndSubmit(user);

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('does not stash twice on a double submit', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof stashSecret>>) => void;
    stash.mockReturnValue(new Promise(r => { resolve = r; }));
    const user = userEvent.setup();
    const { onSubmit } = renderCard();

    await user.type(screen.getByLabelText('Access token'), ACCESS_TOKEN);
    await user.type(screen.getByLabelText('App secret'), APP_SECRET);
    const submit = screen.getByRole('button', { name: 'Submit' });
    fireEvent.click(submit);
    fireEvent.click(submit);

    resolve({ ok: true, credentials_ref: 'SS-0003', fields: ['access_token', 'app_secret'] });
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(stash).toHaveBeenCalledTimes(1);
  });
});
