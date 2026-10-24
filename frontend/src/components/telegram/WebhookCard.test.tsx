// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/services/telegramCommandsApi', () => ({
	refreshWebhookHealth: vi.fn().mockResolvedValue({ ok: false, error: 'x' }),
	setWebhookNow: vi.fn(), deleteWebhookNow: vi.fn(),
}));
import { WebhookCard } from './WebhookCard';

describe('WebhookCard copy', () => {
	it('uses plain product wording', async () => {
		render(<WebhookCard gateway="G" />);
		expect(await screen.findByRole('button', { name: 'Connect to Telegram' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Disconnect' })).toBeInTheDocument();
		expect(screen.queryByText(/webhook/i)).toBeNull();
	});
});
