// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/services/telegramGroupsApi', async (orig) => {
	const real = await orig<typeof import('@/services/telegramGroupsApi')>();
	return { ...real, listJoinRequests: vi.fn(), decideJoinRequest: vi.fn(), listGroups: vi.fn(), getGroupSettings: vi.fn(), leaveGroup: vi.fn() };
});
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() } }));
import * as api from '@/services/telegramGroupsApi';
import { toast } from 'sonner';
import { GroupsTab } from './GroupsTab';

const m = vi.mocked(api);
beforeEach(() => vi.clearAllMocks());

const guard = { join_policy: 'Queue', captcha: true };
const join = (over = {}) => ({
	entry: 'GAE-1', state: 'Pending', chat_id: '-100', chat_title: 'Club', user_id: '42', user_name: '@ada',
	requested_at: '2026-01-01 10:00:00', expires_at: '2999-01-01 10:00:00', expired: false, ...over,
});
const setup = (joins: unknown[], groups: unknown[], note?: string) => {
	m.listJoinRequests.mockResolvedValue({ ok: true, data: { success: true, items: joins as never, guard } });
	m.listGroups.mockResolvedValue({ ok: true, data: { success: true, items: groups as never, guard, note } });
};

describe('GroupsTab', () => {
	it('shows empty states and the guard line', async () => {
		setup([], []);
		render(<GroupsTab gateway="TG-1" />);
		expect(await screen.findByText(/No one is waiting to join/)).toBeTruthy();
		expect(screen.getByText(/not in any group yet/)).toBeTruthy();
		expect(screen.getByTestId('guard-status').textContent).toMatch(/Captcha check: on/);
	});

	it('approve asks for confirmation before calling the API', async () => {
		setup([join()], []);
		m.decideJoinRequest.mockResolvedValue({ ok: true, data: { success: true } });
		render(<GroupsTab gateway="TG-1" />);
		fireEvent.click(await screen.findByText('Approve'));
		expect(m.decideJoinRequest).not.toHaveBeenCalled();
		await screen.findByText('Approve this request?');
		const buttons = screen.getAllByRole('button', { name: 'Approve' });
		fireEvent.click(buttons[buttons.length - 1]);
		await waitFor(() => expect(m.decideJoinRequest).toHaveBeenCalledWith('TG-1', 'GAE-1', 'approve'));
	});

	it('surfaces a server refusal and disables expired requests', async () => {
		setup([join({ expired: true })], []);
		render(<GroupsTab gateway="TG-1" />);
		const btn = (await screen.findByText('Approve')) as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
		expect(toast.error).not.toHaveBeenCalled();
	});

	it('lists groups and loads bot rights', async () => {
		setup([], [{ chat_id: '-100', title: 'Club', status: 'member', since: null }]);
		m.getGroupSettings.mockResolvedValue({
			ok: true, data: { success: true, chat_id: '-100', title: 'Club', type: 'supergroup', admins: [{ user_id: '1', name: 'Boss', is_bot: false, status: 'creator' }], bot: { status: 'administrator', rights: { can_invite_users: true } } },
		});
		render(<GroupsTab gateway="TG-1" />);
		fireEvent.click(await screen.findByText('Check rights'));
		expect(await screen.findByText('Admin')).toBeTruthy();
		expect(screen.getByText(/Boss/)).toBeTruthy();
	});
});
