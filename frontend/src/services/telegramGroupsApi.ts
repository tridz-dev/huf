import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { unwrap, type Result } from '@/services/telegramApi';

/** Typed client for the Telegram Groups & joins tab (huf/ai/telegram_management_groups.py). */
const BASE = 'huf.ai.telegram_management_groups';

export interface GuardStatus { join_policy: 'Queue' | 'Decline' | 'Agent' | string; captcha: boolean }

export interface JoinRequest {
	entry: string;
	state: string;
	chat_id: string;
	chat_title: string;
	user_id: string;
	user_name: string;
	requested_at: string;
	expires_at: string | null;
	expired: boolean;
}

export interface KnownGroup {
	chat_id: string;
	title: string;
	status: 'member' | 'removed';
	since: string | null;
}

export interface GroupSettings {
	chat_id: string;
	title: string;
	type: string;
	admins: { user_id: string; name: string; is_bot: boolean; status: string }[];
	bot: { status: string; rights: Record<string, boolean> };
}

async function req<T>(verb: 'get' | 'post', method: string, args: Record<string, unknown>): Promise<Result<T>> {
	try {
		return unwrap<T>(await call[verb](`${BASE}.${method}`, args));
	} catch (e) {
		return { ok: false, error: getFrappeErrorMessage(e) };
	}
}

export const listJoinRequests = (gateway: string, state = 'Pending') =>
	req<{ success: boolean; items: JoinRequest[]; guard: GuardStatus }>('get', 'list_join_requests', { gateway, state });
export const decideJoinRequest = (gateway: string, entry: string, decision: 'approve' | 'decline') =>
	req<{ success: boolean }>('post', 'decide_join_request', { gateway, entry, decision });
export const listGroups = (gateway: string) =>
	req<{ success: boolean; items: KnownGroup[]; guard: GuardStatus; note?: string }>('get', 'list_groups', { gateway });
export const getGroupSettings = (gateway: string, chatId: string) =>
	req<GroupSettings & { success: boolean }>('get', 'get_group_settings', { gateway, chat_id: chatId });
export const leaveGroup = (gateway: string, chatId: string) =>
	req<{ success: boolean }>('post', 'leave_group', { gateway, chat_id: chatId, confirm: 1 });

export const BOT_RIGHT_LABEL: Record<string, string> = {
	can_invite_users: 'Invite users', can_delete_messages: 'Delete messages', can_restrict_members: 'Restrict members',
	can_pin_messages: 'Pin messages', can_change_info: 'Change info', can_promote_members: 'Add admins', can_manage_chat: 'Manage chat',
};

/** One plain sentence describing how new join requests are handled. */
export function guardSummary(g: GuardStatus | null): string {
	if (!g) return '';
	const policy = g.join_policy === 'Decline' ? 'New join requests are declined automatically.'
		: g.join_policy === 'Agent' ? 'The default agent reviews new join requests.'
		: 'New join requests wait here for an admin.';
	return `${policy} Captcha check: ${g.captcha ? 'on' : 'off'}.`;
}
