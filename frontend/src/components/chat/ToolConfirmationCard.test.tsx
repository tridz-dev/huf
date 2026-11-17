// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { toast } from 'sonner';

import { ToolConfirmationCard } from './ToolConfirmationCard';
import { ChatMessage } from './ChatMessage';
import {
	getConfirmationErrorCode,
	confirmationErrorMessage,
	parseConfirmationRequest,
	parseExpiresAt,
	type ToolConfirmation,
} from '@/services/toolConfirmationApi';
import { call } from '@/lib/frappe-sdk';

vi.mock('sonner', () => ({ toast: { info: vi.fn(), success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/frappe-sdk', () => ({
	call: { post: vi.fn(), get: vi.fn() },
	db: { getDoc: vi.fn(), getDocList: vi.fn().mockResolvedValue([]) },
	auth: { getLoggedInUser: vi.fn() },
	frappe: {},
}));

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

const pending: ToolConfirmation = {
	type: 'confirmation_request',
	id: 'ATC-2026-00001',
	tool: 'gateway_send',
	state: 'pending',
	summary: { action: 'Send WhatsApp broadcast', recipient_count: 120, template: 'promo_nov', channel: 'whatsapp', sample: 'Hi Asha, ...' },
	expires_at: '2026-11-17T10:15:00+00:00',
};
const T0 = Date.parse('2026-11-17T10:10:00+00:00');

describe('ToolConfirmationCard', () => {
	it('renders summary, countdown and enabled buttons when pending', () => {
		render(<ToolConfirmationCard confirmation={pending} now={() => T0} />);
		expect(screen.getByText('Send WhatsApp broadcast')).toBeTruthy();
		expect(screen.getByText('120')).toBeTruthy();
		expect(screen.getByText('promo_nov')).toBeTruthy();
		expect(screen.getByText('whatsapp')).toBeTruthy();
		expect(screen.getByText('Hi Asha, ...')).toBeTruthy();
		expect(screen.getByTestId('confirmation-countdown').textContent).toContain('5:00');
		expect((screen.getByRole('button', { name: 'Approve' }) as HTMLButtonElement).disabled).toBe(false);
	});

	it.each(['executed', 'denied', 'expired', 'failed', 'approved'] as const)('hides actions when state=%s', (state) => {
		render(<ToolConfirmationCard confirmation={{ ...pending, state }} now={() => T0} />);
		expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Deny' })).toBeNull();
		expect(screen.getByTestId('tool-confirmation-card').getAttribute('data-state')).toBe(state);
	});

	it('treats a past expires_at as expired locally', () => {
		render(<ToolConfirmationCard confirmation={pending} now={() => T0 + 10 * 60_000} />);
		expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
		expect(screen.getByTestId('confirmation-state').textContent).toBe('Expired');
	});

	it('Approve calls decide with approve=1 and reports the returned confirmation', async () => {
		const user = userEvent.setup();
		const onUpdated = vi.fn();
		const onDecided = vi.fn();
		vi.mocked(call.post).mockResolvedValue({ message: { confirmation: { ...pending, state: 'executed' }, result: {} } });
		render(<ToolConfirmationCard confirmation={pending} now={() => T0} onUpdated={onUpdated} onDecided={onDecided} />);
		await user.click(screen.getByRole('button', { name: 'Approve' }));
		expect(call.post).toHaveBeenCalledWith('huf.ai.tool_confirmation.decide', { id: pending.id, approve: 1 });
		await waitFor(() => expect(onDecided).toHaveBeenCalled());
		expect(onUpdated.mock.calls[0][0].state).toBe('executed');
	});

	it('Deny calls decide with approve=0', async () => {
		const user = userEvent.setup();
		vi.mocked(call.post).mockResolvedValue({ message: { confirmation: { ...pending, state: 'denied' }, result: null } });
		render(<ToolConfirmationCard confirmation={pending} now={() => T0} />);
		await user.click(screen.getByRole('button', { name: 'Deny' }));
		expect(call.post).toHaveBeenCalledWith('huf.ai.tool_confirmation.decide', { id: pending.id, approve: 0 });
	});

	it('maps an error code to a clear toast and locks the card', async () => {
		const user = userEvent.setup();
		const onUpdated = vi.fn();
		vi.mocked(call.post).mockRejectedValue({ exc_type: 'ValidationError', message: 'confirmation_expired: request expired' });
		render(<ToolConfirmationCard confirmation={pending} now={() => T0} onUpdated={onUpdated} />);
		await user.click(screen.getByRole('button', { name: 'Approve' }));
		await waitFor(() => expect(toast.error).toHaveBeenCalledWith('This approval request expired. Ask the agent to try again.'));
		expect(onUpdated.mock.calls[0][0].state).toBe('expired');
	});
});

describe('expiry parsing and sending state', () => {
	it('parses ISO with offset as an absolute instant', () => {
		expect(parseExpiresAt('2026-11-17T10:15:00+00:00')).toBe(Date.UTC(2026, 10, 17, 10, 15));
		expect(parseExpiresAt('2026-11-17T12:15:00+02:00')).toBe(Date.UTC(2026, 10, 17, 10, 15));
	});
	it('treats legacy naive strings as UTC and rejects junk', () => {
		expect(parseExpiresAt('2026-11-17 10:15:00')).toBe(Date.UTC(2026, 10, 17, 10, 15));
		expect(parseExpiresAt('nope')).toBeNull();
		expect(parseExpiresAt(null)).toBeNull();
	});
	it('shows Sending… for approved without actions', () => {
		render(<ToolConfirmationCard confirmation={{ ...pending, state: 'approved' }} now={() => T0} />);
		expect(screen.getByTestId('confirmation-state').textContent).toBe('Sending…');
		expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
	});
});

describe('error mapping', () => {
	it.each([
		['confirmation_expired', 'expired'],
		['confirmation_already_decided', 'already_decided'],
		['confirmation_args_changed', 'args_changed'],
		['confirmation_role_denied', 'role_denied'],
		['confirmation_forbidden', 'forbidden'],
	])('%s -> %s', (raw, code) => {
		expect(getConfirmationErrorCode({ _server_messages: JSON.stringify([`${raw}: x`]) })).toBe(code);
		expect(getConfirmationErrorCode(new Error(`${raw}: x`))).toBe(code);
		expect(confirmationErrorMessage(new Error(raw))).not.toMatch(/confirmation_/);
	});
	it('falls back for unknown errors', () => {
		expect(getConfirmationErrorCode(new Error('boom'))).toBeNull();
		expect(confirmationErrorMessage(new Error('boom'))).toMatch(/try again/i);
	});
});

describe('history rendering', () => {
	const json = JSON.stringify({ ...pending, args: { otp: '123456' }, requires_confirmation: true });
	it('parses plain and embedded JSON and drops unknown/secret keys', () => {
		const a = parseConfirmationRequest(json);
		const b = parseConfirmationRequest(`Tool Result:\n${json}\nthanks`);
		expect(a?.id).toBe(pending.id);
		expect(b?.id).toBe(pending.id);
		expect(JSON.stringify(a)).not.toContain('123456');
		expect(parseConfirmationRequest('{"type":"other"}')).toBeNull();
	});

	it('renders a Tool Result confirmation_request message as a card, even with tool details hidden', () => {
		render(
			<MemoryRouter>
				<ChatMessage
					status="ready"
					onFeedback={() => {}}
					scrollToBottomAfterPaint={() => {}}
					message={{ key: 'm1', from: 'assistant', kind: 'Tool Result', versions: [{ id: 'v', content: json }] }}
					showToolExecutionDetails={false}
				/>
			</MemoryRouter>
		);
		expect(screen.getByTestId('tool-confirmation-card')).toBeTruthy();
		expect(screen.queryByText(/123456/)).toBeNull();
	});

	it('uses the override state over the history snapshot', () => {
		render(
			<MemoryRouter>
				<ChatMessage
					status="ready"
					onFeedback={() => {}}
					scrollToBottomAfterPaint={() => {}}
					message={{ key: 'm1', from: 'assistant', kind: 'Tool Result', versions: [{ id: 'v', content: json }] }}
					confirmationOverrides={{ [pending.id]: { ...pending, state: 'denied' } }}
				/>
			</MemoryRouter>
		);
		expect(screen.getByTestId('tool-confirmation-card').getAttribute('data-state')).toBe('denied');
		expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
	});
});
