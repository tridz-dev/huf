// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/services/telegramCommandsApi', async (orig) => ({
	...(await orig<typeof import('@/services/telegramCommandsApi')>()),
	refreshWebhookHealth: vi.fn(),
	setWebhookNow: vi.fn(),
	deleteWebhookNow: vi.fn(),
	checkToken: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import * as api from '@/services/telegramCommandsApi';
import { TokenCheckCard } from './TokenCheckCard';
import { WebhookCard } from './WebhookCard';

const HOOK: api.WebhookSummary = {
	url: 'https://old/h',
	url_matches: false,
	pending_update_count: 4,
	last_error_date: null,
	last_error_message: '',
	allowed_updates: ['message'],
	allowed_updates_ok: false,
	expected_url: 'https://new/h',
	expected_allowed_updates: ['message', 'callback_query'],
};

beforeEach(() => {
	vi.clearAllMocks();
	vi.mocked(api.refreshWebhookHealth).mockResolvedValue({ ok: true, data: { webhook: HOOK } });
	vi.mocked(api.setWebhookNow).mockResolvedValue({ ok: true, data: { webhook: { ...HOOK, url: HOOK.expected_url, url_matches: true } } });
});

describe('WebhookCard', () => {
	it('shows state and does not set the webhook until confirmed', async () => {
		render(<WebhookCard gateway="G" />);
		expect(await screen.findByText('https://old/h')).toBeInTheDocument();
		expect(screen.getByText('Waiting updates').parentElement).toHaveTextContent('4');
		await userEvent.click(screen.getByRole('button', { name: 'Set webhook' }));
		expect(await screen.findByText('Take over this bot?')).toBeInTheDocument();
		expect(api.setWebhookNow).not.toHaveBeenCalled();
		await userEvent.click(screen.getAllByRole('button', { name: 'Set webhook' }).at(-1)!);
		await waitFor(() => expect(api.setWebhookNow).toHaveBeenCalledWith('G', false));
	});

	it('cancel does nothing', async () => {
		render(<WebhookCard gateway="G" />);
		await screen.findByText('https://old/h');
		await userEvent.click(screen.getByRole('button', { name: 'Set webhook' }));
		await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
		expect(api.setWebhookNow).not.toHaveBeenCalled();
	});
});

describe('TokenCheckCard', () => {
	it('reports a rejected token without any token text', async () => {
		vi.mocked(api.checkToken).mockResolvedValue({ ok: true, data: { check: { valid: false, reason: 'Unauthorized' } } });
		render(<TokenCheckCard gateway="G" />);
		await userEvent.click(screen.getByRole('button', { name: 'Check token' }));
		expect(await screen.findByRole('note')).toHaveTextContent('Unauthorized');
	});

	it('shows the bot username when valid', async () => {
		vi.mocked(api.checkToken).mockResolvedValue({ ok: true, data: { check: { valid: true, username: 'tbot' } } });
		render(<TokenCheckCard gateway="G" />);
		await userEvent.click(screen.getByRole('button', { name: 'Check token' }));
		expect(await screen.findByText(/@tbot/)).toBeInTheDocument();
	});
});
