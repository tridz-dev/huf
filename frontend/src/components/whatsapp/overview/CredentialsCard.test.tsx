// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { TokenCheckSummary } from '@/services/whatsappHealthApi';
import { CredentialsCard, type CredentialsCardProps } from './CredentialsCard';

const check = (over: Partial<TokenCheckSummary> = {}): TokenCheckSummary => ({
	valid: true,
	token_type: 'SYSTEM_USER',
	expires_at: null,
	missing_scopes: [],
	waba_ids: [],
	phone: null,
	webhook_subscribed: true,
	checked_at: null,
	source: 'debug_token',
	...over,
});

const base: CredentialsCardProps = {
	accessTokenPresent: true,
	appSecretPresent: false,
	verifyTokenPresent: true,
	appIdPresent: true,
	tokenCheck: null,
	onCheckToken: vi.fn(),
};

describe('CredentialsCard', () => {
	it('shows presence only', () => {
		render(<CredentialsCard {...base} />);
		expect(screen.getAllByText('Saved')).toHaveLength(3);
		expect(screen.getAllByText('Missing')).toHaveLength(1);
		expect(screen.getByText('Not checked yet')).toBeInTheDocument();
	});

	it('renders a valid system token result', async () => {
		const user = userEvent.setup();
		render(<CredentialsCard {...base} onCheckToken={async () => check()} />);
		await user.click(screen.getByRole('button', { name: 'Check token' }));
		expect(await screen.findByText('Token is valid')).toBeInTheDocument();
		expect(screen.getByText(/Never expires/)).toBeInTheDocument();
		expect(screen.getByText('Webhook subscribed: Yes')).toBeInTheDocument();
	});

	it('renders invalid result with plain-word permissions and unknown webhook', async () => {
		const user = userEvent.setup();
		const result = check({
			valid: false,
			token_type: 'USER',
			expires_at: '2030-01-01T00:00:00Z',
			missing_scopes: ['whatsapp_business_messaging', 'whatsapp_business_management'],
			webhook_subscribed: null,
		});
		render(<CredentialsCard {...base} onCheckToken={async () => result} />);
		await user.click(screen.getByRole('button', { name: 'Check token' }));
		expect(await screen.findByText('Token is not valid')).toBeInTheDocument();
		expect(screen.getByText('Send and receive messages')).toBeInTheDocument();
		expect(screen.getByText('Manage templates and account')).toBeInTheDocument();
		expect(screen.getByText(/User token\. Expires/)).toBeInTheDocument();
		expect(screen.getByText('Webhook subscribed: Not checked yet')).toBeInTheDocument();
	});

	it('shows a friendly rate-limit message', async () => {
		const user = userEvent.setup();
		render(<CredentialsCard {...base} onCheckToken={() => Promise.reject(new Error('429 Too Many Requests'))} />);
		await user.click(screen.getByRole('button', { name: 'Check token' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('Wait a minute');
	});

	it('shows other errors and disables the button while checking', async () => {
		const user = userEvent.setup();
		let reject!: (e: Error) => void;
		const pending = new Promise<TokenCheckSummary>((_, r) => (reject = r));
		render(<CredentialsCard {...base} onCheckToken={() => pending} />);
		await user.click(screen.getByRole('button', { name: 'Check token' }));
		expect(screen.getByRole('button', { name: 'Checking…' })).toBeDisabled();
		reject(new Error('Meta is down'));
		expect(await screen.findByRole('alert')).toHaveTextContent('Meta is down');
	});

	it('shows rotation help when opened', async () => {
		const user = userEvent.setup();
		render(<CredentialsCard {...base} integrationSettingsHref="/s" />);
		await user.click(screen.getByText('Rotating a secret'));
		expect(screen.getByRole('link', { name: 'integration settings' })).toHaveAttribute('href', '/s');
	});

	it('flags a rejected token and offers a replace action instead of Saved', () => {
		render(<CredentialsCard {...base} tokenCheck={check({ valid: false })} integrationSettingsHref="/app/gateway/GW" />);
		expect(screen.getByText('Meta rejected this token')).toBeInTheDocument();
		expect(screen.getAllByText('Saved')).toHaveLength(2);
		expect(screen.getByRole('link', { name: 'Replace access token' })).toHaveAttribute('href', '/app/gateway/GW');
		expect(screen.queryByText('Not checked yet')).toBeNull();
	});
});
