// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import type { TokenCheckSummary } from '@/services/whatsappHealthApi';
import { TokenCard } from './TokenCard';

const check = (over: Partial<TokenCheckSummary> = {}): TokenCheckSummary => ({
	valid: true,
	token_type: 'SYSTEM_USER',
	expires_at: null,
	missing_scopes: [],
	waba_ids: [],
	phone: null,
	webhook_subscribed: null,
	checked_at: null,
	source: 'debug_token',
	...over,
});

describe('TokenCard', () => {
	it.each([null, undefined])('prompts for a first check when there is none (%s)', (value) => {
		render(<TokenCard check={value} />);
		expect(screen.getByText(/Not checked yet/)).toBeInTheDocument();
		expect(screen.queryByText('Valid')).toBeNull();
	});

	it('shows a valid token that never expires', () => {
		render(<TokenCard check={check()} />);
		expect(screen.getByText('Valid')).toBeInTheDocument();
		expect(screen.getByText('Never')).toBeInTheDocument();
		expect(screen.queryByText('Reason')).toBeNull();
		expect(screen.queryByText('Webhook')).toBeNull();
	});

	it('explains an invalid token with the message, else the error code', () => {
		const { rerender } = render(<TokenCard check={check({ valid: false, message: 'Session expired' })} />);
		expect(screen.getByText('Not valid')).toBeInTheDocument();
		expect(screen.getByText('Session expired')).toBeInTheDocument();
		rerender(<TokenCard check={check({ valid: false, error_code: 190 })} />);
		expect(screen.getByText('Error 190')).toBeInTheDocument();
		rerender(<TokenCard check={check({ valid: false })} />);
		expect(screen.queryByText('Reason')).toBeNull();
	});

	it('lists missing permissions, webhook state and number quality', () => {
		const { rerender } = render(
			<TokenCard check={check({ missing_scopes: ['a_scope', 'b_scope'], webhook_subscribed: false, phone: { quality: 'GREEN' } })} />,
		);
		expect(screen.getByText('a_scope, b_scope')).toBeInTheDocument();
		expect(screen.getByText('Not subscribed')).toBeInTheDocument();
		expect(screen.getByText('GREEN')).toBeInTheDocument();
		rerender(<TokenCard check={check({ webhook_subscribed: true })} />);
		expect(screen.getByText('Subscribed')).toBeInTheDocument();
	});

	it('tolerates a partial server result with no scopes or webhook field', () => {
		render(<TokenCard check={{ valid: true, checked_at: null } as unknown as TokenCheckSummary} />);
		expect(screen.getByText('Valid')).toBeInTheDocument();
	});

	it('formats the expiry and check times', () => {
		render(<TokenCard check={check({ expires_at: '2030-01-02T03:04:05Z', checked_at: '2026-10-21T10:00:00Z' })} />);
		expect(screen.getByText('Checked')).toBeInTheDocument();
		expect(screen.queryByText('Never')).toBeNull();
	});

	it('says Meta rejected the token and points to Settings', () => {
		render(<TokenCard check={check({ valid: false, checked_at: '2026-10-14T10:00:00Z' })} />);
		expect(screen.getByText(/Meta rejected this token/)).toBeInTheDocument();
		expect(screen.getByText(/Meta rejected this token/)).not.toHaveTextContent(/ on \d+ min ago/);
		expect(screen.getByRole('link', { name: 'Replace it in Settings' })).toHaveAttribute('href', '#credentials');
		expect(screen.queryByText(/Not checked yet/)).toBeNull();
	});
});
