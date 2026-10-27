// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import type { GatewayHealthStatus } from '@/services/whatsappHealthApi';
import { HealthBanner } from './HealthBanner';
import { numberSummary } from './fixturesSolutions';

function gw(over: Partial<GatewayHealthStatus> = {}): GatewayHealthStatus {
	return {
		name: 'GW-1',
		enabled: true,
		health: 'healthy',
		reasons: [],
		next_step: null,
		checklist: [{ code: 'credentials', state: 'done' }],
		webhook_url: '',
		verify_token_present: true,
		access_token_present: true,
		app_secret_present: true,
		app_id_present: true,
		whatsapp_account: null,
		account_phone_mismatch: false,
		phone_number_id: null,
		fallback_template: null,
		fallback_template_language: null,
		fallback_template_approved: null,
		last_event_at: new Date(Date.now() - 4 * 60_000).toISOString(),
		last_error: null,
		events_24h: { received: 5, failed: 0, unrouted: 0, rejected: 0 },
		last_failed_event: null,
		unrouted_phone_ids: [],
		policy: {},
		meta_links: { app_dashboard: null, whatsapp_manager: null, webhook_config: null },
		token_check: null,
		...over,
	};
}

function view(g: GatewayHealthStatus | null, props: Partial<React.ComponentProps<typeof HealthBanner>> = {}) {
	return render(
		<MemoryRouter>
			<HealthBanner gateway={g} onCheck={vi.fn()} {...props} />
		</MemoryRouter>
	);
}

describe('HealthBanner', () => {
	it('healthy: muted status, last message time', () => {
		view(gw());
		expect(screen.getByRole('status')).toHaveTextContent('Working: receiving and replying normally.');
		expect(screen.queryByRole('alert')).toBeNull();
		expect(screen.getByText(/Last message/)).toHaveTextContent('Last message 4 min ago');
	});

	it('degraded: warning alert using backend reason message', () => {
		view(gw({ health: 'degraded', reasons: [{ code: 'send_failing', severity: 'warning', message: 'Replies are failing: 3 in the last 24 hours.' }] }));
		const alert = screen.getByRole('alert');
		expect(alert).toHaveTextContent('Replies are failing: 3 in the last 24 hours.');
		expect(alert).toHaveClass('bg-warning-tint');
	});

	it('degraded: falls back to friendly copy when message is empty', () => {
		view(gw({ health: 'degraded', events_24h: { received: 1, failed: 2, unrouted: 0, rejected: 0 }, reasons: [{ code: 'x', severity: 'warning', message: '' }] }));
		expect(screen.getByRole('alert')).toHaveTextContent('Replies are failing: 2 in the last 24 hours.');
	});

	it('blocked: destructive alert with a single next-step link', () => {
		view(gw({
			health: 'blocked',
			reasons: [{ code: 'access_token_missing', severity: 'error', message: '' }],
			next_step: { code: 'token', label: 'Update token', action_url: 'https://developers.facebook.com/apps' },
		}));
		const alert = screen.getByRole('alert');
		expect(alert).toHaveClass('bg-destructive-tint');
		expect(alert).toHaveTextContent('Blocked: add the access token from Meta.');
		const link = screen.getByRole('link', { name: /Update token/ });
		expect(link).toHaveAttribute('href', 'https://developers.facebook.com/apps');
		expect(link).toHaveAttribute('target', '_blank');
		expect(link).toHaveAttribute('rel', 'noopener noreferrer');
	});

	it('blocked: internal action url uses a router link without target', () => {
		view(gw({ health: 'blocked', next_step: { code: 'c', label: 'Fix it', action_url: '/settings/whatsapp' } }));
		const link = screen.getByRole('link', { name: 'Fix it' });
		expect(link).toHaveAttribute('href', '/settings/whatsapp');
		expect(link).not.toHaveAttribute('target');
	});

	it('not_set_up shows the finish setup title', () => {
		view(gw({ health: 'not_set_up', last_event_at: null }));
		expect(screen.getByText('Finish setup to start receiving messages')).toBeInTheDocument();
		expect(screen.getByText('No messages received yet')).toBeInTheDocument();
	});

	it('disabled: neutral with a Turn on action', async () => {
		const onTurnOn = vi.fn();
		view(gw({ health: 'disabled', enabled: false }), { onTurnOn });
		await userEvent.click(screen.getByRole('button', { name: 'Turn on' }));
		expect(onTurnOn).toHaveBeenCalledOnce();
	});

	it('renders check badges, including token only when token_check exists', () => {
		const { unmount } = view(gw());
		expect(screen.queryByText(/Token valid/)).toBeNull();
		unmount();
		view(gw({ token_check: { valid: true, token_type: null, expires_at: null, missing_scopes: [], waba_ids: [], phone: null, webhook_subscribed: null, checked_at: null, source: null } }));
		for (const l of ['Enabled', 'Credentials', 'Token valid', 'Receiving', 'Delivering']) {
			expect(screen.getByText(l)).toBeInTheDocument();
		}
	});

	it('Check now calls onCheck and disables while checking', async () => {
		const onCheck = vi.fn();
		const { unmount } = view(gw(), { onCheck });
		await userEvent.click(screen.getByRole('button', { name: 'Check now' }));
		expect(onCheck).toHaveBeenCalledOnce();
		unmount();
		view(gw(), { checking: true });
		expect(screen.getByRole('button', { name: 'Checking…' })).toBeDisabled();
	});

	it('loading renders a busy skeleton', () => {
		view(null, { loading: true });
		expect(screen.getByLabelText('Loading health')).toHaveAttribute('aria-busy', 'true');
	});

	it('a rejected token reads Token rejected in red and Credentials follows the blocked step', () => {
		view(gw({
			checklist: [{ code: 'credentials', state: 'blocked' }],
			token_check: { valid: false, token_type: null, expires_at: null, missing_scopes: [], waba_ids: [], phone: null, webhook_subscribed: null, checked_at: null, source: null },
		}));
		expect(screen.getByText('Token rejected')).toBeInTheDocument();
		expect(screen.queryByText('Token valid')).toBeNull();
		expect(screen.getByText('Token rejected').className).toMatch(/destructive/);
		expect(screen.getByText('Credentials').className).toMatch(/destructive/);
	});

	describe('solution blame', () => {
		const renderBanner = (health: 'healthy' | 'degraded', summary = numberSummary()) =>
			render(
				<MemoryRouter>
					<HealthBanner gateway={gw({ health })} onCheck={vi.fn()} numberSummary={summary} />
				</MemoryRouter>
			);

		it('names the solution behind most sends when quality is not healthy, without claiming cause', () => {
			renderBanner('degraded');
			expect(screen.getByRole('link', { name: 'Orders' })).toHaveAttribute('href', '/solutions/orders');
			expect(screen.getByText(/Most of today's sends came from/)).toBeInTheDocument();
			expect(screen.getByText(/91% of sends/)).toBeInTheDocument();
			expect(screen.getByText(/Quality is medium/)).toBeInTheDocument();
			expect(screen.queryByText(/caused/i)).not.toBeInTheDocument();
		});

		it('shows nothing about blame or rating when healthy and quality is good', () => {
			renderBanner('healthy', numberSummary({ quality: { rating: 'High', source: 'meta' } }));
			expect(screen.queryByText(/Most of today's sends/)).not.toBeInTheDocument();
		});

		it('shows no rating text when quality source is unknown', () => {
			renderBanner('degraded', numberSummary({ quality: { rating: 'Low', source: 'unknown' } }));
			expect(screen.queryByText(/Quality is/)).not.toBeInTheDocument();
			expect(screen.getByText(/Most of today's sends/)).toBeInTheDocument();
		});

		it('omits the blame line when there is no blame', () => {
			renderBanner('degraded', numberSummary({ blame: null }));
			expect(screen.queryByText(/Most of today's sends/)).not.toBeInTheDocument();
		});
	});
});
