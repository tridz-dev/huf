// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { TelegramHealth } from '@/services/telegramApi';
import { HealthBanner, typingLine } from './HealthBanner';

const PASS = [
	{ id: 'bot_reachable', label: 'x', ok: true, state: 'pass' as const, hint: '' },
	{ id: 'webhook_url', label: 'x', ok: true, state: 'pass' as const, hint: '' },
	{ id: 'webhook_error', label: 'x', ok: true, state: 'pass' as const, hint: '' },
];

function h(over: Partial<TelegramHealth> = {}): TelegramHealth {
	return {
		name: 'TG-1',
		enabled: true,
		health: 'healthy',
		checks: PASS,
		checklist: [],
		pending_update_count: 0,
		last_event_at: new Date(Date.now() - 4 * 60_000).toISOString(),
		...over,
	};
}

describe('Telegram HealthBanner', () => {
	it('healthy: status with last message time', () => {
		render(<HealthBanner health={h()} onCheck={vi.fn()} />);
		expect(screen.getByRole('status')).toHaveTextContent('Working: receiving and replying normally.');
		expect(screen.getByText(/Last message/)).toHaveTextContent('Last message 4 min ago');
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it('degraded: alert with plain wording, never raw API text', () => {
		const checks = [...PASS.slice(0, 1), { id: 'webhook_url', label: 'x', ok: false, state: 'fail' as const, hint: 'getWebhookInfo failed' }];
		render(<HealthBanner health={h({ health: 'degraded', checks })} onCheck={vi.fn()} />);
		const alert = screen.getByRole('alert');
		expect(alert).toHaveTextContent('Telegram is not sending messages to this site yet.');
		expect(alert).not.toHaveTextContent('getWebhookInfo');
	});

	it('blocked: rejected token pill', () => {
		const checks = [{ id: 'bot_reachable', label: 'x', ok: false, state: 'fail' as const, hint: '' }];
		render(<HealthBanner health={h({ health: 'blocked', checks })} onCheck={vi.fn()} />);
		expect(screen.getByRole('alert')).toHaveTextContent('Telegram accepts the bot token.');
		expect(screen.getByText('Token rejected')).toBeInTheDocument();
	});

	it('disabled: turn on button; check now fires', async () => {
		const onTurnOn = vi.fn();
		const onCheck = vi.fn();
		render(<HealthBanner health={h({ health: 'disabled', enabled: false, last_event_at: null })} onCheck={onCheck} onTurnOn={onTurnOn} />);
		await userEvent.click(screen.getByRole('button', { name: 'Turn on' }));
		await userEvent.click(screen.getByRole('button', { name: 'Check now' }));
		expect(onTurnOn).toHaveBeenCalled();
		expect(onCheck).toHaveBeenCalled();
		expect(screen.getByText('No messages received yet')).toBeInTheDocument();
	});

	it('loading shows a busy skeleton; checking disables the button', () => {
		const { rerender } = render(<HealthBanner health={null} onCheck={vi.fn()} />);
		expect(screen.getByLabelText('Loading health')).toBeInTheDocument();
		rerender(<HealthBanner health={h()} checking onCheck={vi.fn()} />);
		expect(screen.getByRole('button', { name: 'Checking…' })).toBeDisabled();
	});
});

describe('Telegram HealthBanner typing line', () => {
	it('shows last sent time and 24h count when typing is on', () => {
		const typing = { last_sent_at: '2026-10-23 12:03:41', sent_count_24h: 18, last_error: null, last_error_at: null, keepalive_ticks: 4 };
		render(<HealthBanner health={h({ typing })} onCheck={vi.fn()} />);
		expect(screen.getByText('Typing indicator: last sent 12:03:41, 18 in 24h')).toBeInTheDocument();
	});

	it('is hidden when typing is off (null block)', () => {
		render(<HealthBanner health={h({ typing: null })} onCheck={vi.fn()} />);
		expect(screen.queryByText(/Typing indicator/)).toBeNull();
	});

	it('formats never-sent and failure time without internal error kinds', () => {
		expect(typingLine({ last_sent_at: null, sent_count_24h: 0, last_error: 'blocked', last_error_at: '2026-10-23 09:00:02', keepalive_ticks: 0 })).toBe(
			'Typing indicator: not sent yet · last failure 09:00:02',
		);
	});
});
