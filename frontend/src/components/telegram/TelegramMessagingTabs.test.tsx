// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/services/telegramMessagesApi', async (orig) => {
	const real = await orig<typeof import('@/services/telegramMessagesApi')>();
	return {
		...real,
		listMessages: vi.fn(), getMessage: vi.fn(), listAccess: vi.fn(), approveAccess: vi.fn(), revokeAccess: vi.fn(),
		listBindings: vi.fn(), revokeBinding: vi.fn(), createBindingCodeForMe: vi.fn(), listBusinessConnections: vi.fn(),
		listSendTargets: vi.fn(), sendTelegramMessage: vi.fn(), uploadPrivateFile: vi.fn(),
	};
});
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() } }));
import * as api from '@/services/telegramMessagesApi';
import { AccessTab } from './AccessTab';
import { BindingsTab } from './BindingsTab';
import { BusinessConnectionsCard } from './BusinessConnectionsCard';
import { MessagesTab } from './MessagesTab';
import { SendPanel } from './SendPanel';

const m = vi.mocked(api);
beforeEach(() => vi.clearAllMocks());

const msg = (over = {}) => ({
	name: 'EV-1', received_at: '2026-01-01 10:00:00', kind: 'text', text: 'hello bot', sender_id: '42', sender_name: 'Ada',
	status: 'Completed', reply_status: 'sent', error: '', agent_run: null, agent: null, ...over,
}) as never;

describe('MessagesTab', () => {
	it('lists messages, loads more and opens the detail', async () => {
		m.listMessages.mockResolvedValueOnce({ ok: true, data: { success: true, items: [msg()], next_cursor: 'c1', has_more: true } });
		m.listMessages.mockResolvedValueOnce({ ok: true, data: { success: true, items: [msg({ name: 'EV-2', text: 'second' })], next_cursor: null, has_more: false } });
		m.getMessage.mockResolvedValue({ ok: true, data: { success: true, message: { ...(msg() as object), update_kind: 'message', chat_id: '42', attachments: [], reply: { status: 'sent', message_id: '5', parts: [{ message_id: 5 }], error: '' } } as never } });
		render(<MessagesTab gateway="TG-1" />);
		await screen.findByText('hello bot');
		fireEvent.click(screen.getByText('Load more'));
		await screen.findByText('second');
		expect(m.listMessages).toHaveBeenLastCalledWith('TG-1', {}, 'c1');
		fireEvent.click(screen.getByText('hello bot'));
		await screen.findByText('message');
		expect(m.getMessage).toHaveBeenCalledWith('TG-1', 'EV-1');
	});

	it('shows an error and an empty state', async () => {
		m.listMessages.mockResolvedValue({ ok: false, error: 'Not permitted' });
		render(<MessagesTab gateway="TG-1" />);
		await screen.findByText(/Not permitted/);
	});
});

describe('AccessTab', () => {
	it('approves a pending entry', async () => {
		const entry = { name: 'GAE-1', external_id: '42', display_label: 'Ada', entry_type: 'Sender', state: 'Pending', creation: '2026-01-01 10:00:00' };
		m.listAccess.mockResolvedValue({ ok: true, data: { success: true, items: [entry] } });
		m.approveAccess.mockResolvedValue({ ok: true, data: { success: true } });
		render(<AccessTab gateway="TG-1" />);
		fireEvent.click(await screen.findByText('Approve'));
		await waitFor(() => expect(m.approveAccess).toHaveBeenCalledWith('TG-1', 'GAE-1'));
	});
});

describe('SendPanel', () => {
	it('explains when there is nobody to send to', async () => {
		m.listSendTargets.mockResolvedValue({ ok: true, data: { success: true, items: [] } });
		render(<SendPanel gateway="TG-1" />);
		await screen.findByText(/Nobody to send to yet/);
	});

	it('validates then sends text to a listed target', async () => {
		m.listSendTargets.mockResolvedValue({ ok: true, data: { success: true, items: [{ chat_id: '42', label: 'My bound chat', source: 'binding' }] } });
		m.sendTelegramMessage.mockResolvedValue({ ok: true, data: { success: true, message_ids: [1] } });
		render(<SendPanel gateway="TG-1" />);
		const send = await screen.findByText('Send');
		await waitFor(() => expect(send).not.toBeDisabled());
		fireEvent.click(send);
		expect(await screen.findByRole('alert')).toHaveTextContent('Write a message first.');
		fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'hi' } });
		fireEvent.click(send);
		await waitFor(() => expect(m.sendTelegramMessage).toHaveBeenCalledWith('TG-1', '42', 'hi', 'text', undefined));
	});
});

describe('BindingsTab', () => {
	it('lists bindings and shows a minted code once', async () => {
		m.listBindings.mockResolvedValue({ ok: true, data: { success: true, items: [{ name: 'B-1', frappe_user: 'a@x.com', telegram_user_id: '42', role_scope: 'Admin', is_active: true, paired_at: null, last_seen_at: null }] } });
		m.createBindingCodeForMe.mockResolvedValue({ ok: true, data: { success: true, code: 'HUF-SECRET', expires_in: 600, instructions: 'Send /start HUF-SECRET' } });
		m.revokeBinding.mockResolvedValue({ ok: true, data: { success: true } });
		render(<BindingsTab gateway="TG-1" />);
		await screen.findByText('a@x.com');
		fireEvent.click(screen.getByText('Bind my Telegram'));
		fireEvent.click(await screen.findByText('Create code'));
		await screen.findByText('HUF-SECRET');
		fireEvent.click(screen.getByText('Done'));
		await waitFor(() => expect(screen.queryByText('HUF-SECRET')).not.toBeInTheDocument());
		fireEvent.click(screen.getByText('Revoke'));
		await waitFor(() => expect(m.revokeBinding).toHaveBeenCalledWith('TG-1', 'B-1'));
	});
});

describe('BusinessConnectionsCard', () => {
	it('shows state and rights, or an empty note', async () => {
		m.listBusinessConnections.mockResolvedValueOnce({ ok: true, data: { success: true, items: [{ id: 'c1', owner_id: '7', owner_name: 'Grace', enabled: true, rights: { can_reply: true, can_read_messages: false } }] } });
		const { unmount } = render(<BusinessConnectionsCard gateway="TG-1" />);
		await screen.findByText('Grace');
		expect(screen.getByText('Reply: Yes')).toBeInTheDocument();
		expect(screen.getByText('Read messages: No')).toBeInTheDocument();
		unmount();
		m.listBusinessConnections.mockResolvedValueOnce({ ok: true, data: { success: true, items: [] } });
		render(<BusinessConnectionsCard gateway="TG-1" />);
		await screen.findByText(/No business accounts/);
	});
});
