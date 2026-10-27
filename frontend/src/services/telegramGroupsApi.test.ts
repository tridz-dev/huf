import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() } }));
import { call } from '@/lib/frappe-sdk';
import { decideJoinRequest, guardSummary, leaveGroup, listJoinRequests } from './telegramGroupsApi';

beforeEach(() => vi.clearAllMocks());

describe('telegram groups api', () => {
	it('reads with GET and decisions use POST', async () => {
		vi.mocked(call.get).mockResolvedValue({ message: { success: true, items: [], guard: { join_policy: 'Queue', captcha: false } } } as never);
		await listJoinRequests('TG-1');
		expect(call.get).toHaveBeenCalledWith('huf.ai.telegram_management_groups.list_join_requests', { gateway: 'TG-1', state: 'Pending' });
		vi.mocked(call.post).mockResolvedValue({ message: { success: false, error: 'expired', message: 'This join request has expired.' } } as never);
		expect(await decideJoinRequest('TG-1', 'E', 'decline')).toEqual({ ok: false, error: 'This join request has expired.' });
		expect(call.post).toHaveBeenCalledWith('huf.ai.telegram_management_groups.decide_join_request', { gateway: 'TG-1', entry: 'E', decision: 'decline' });
	});

	it('leave always sends confirm', async () => {
		vi.mocked(call.post).mockResolvedValue({ message: { success: true } } as never);
		await leaveGroup('TG-1', '-100');
		expect(call.post).toHaveBeenCalledWith('huf.ai.telegram_management_groups.leave_group', { gateway: 'TG-1', chat_id: '-100', confirm: 1 });
	});

	it('guard summary is plain', () => {
		expect(guardSummary({ join_policy: 'Decline', captcha: false })).toMatch(/declined automatically.*off/);
		expect(guardSummary(null)).toBe('');
	});
});
