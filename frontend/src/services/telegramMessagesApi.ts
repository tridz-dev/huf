import { call, file } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { unwrap, type Result } from '@/services/telegramApi';

/** Typed client for the Telegram Messages, Access, Send and Bindings tabs (huf/ai/telegram_management_messages.py). */
const BASE = 'huf.ai.telegram_management_messages';

export const MESSAGE_KINDS = ['text', 'media', 'voice', 'callback', 'reaction', 'business', 'inline', 'guest', 'join'] as const;
export type MessageKind = (typeof MESSAGE_KINDS)[number];
export const KIND_LABEL: Record<MessageKind, string> = {
	text: 'Text', media: 'Photo or file', voice: 'Voice', callback: 'Button press', reaction: 'Reaction',
	business: 'Business', inline: 'Inline', guest: 'Guest', join: 'Join request',
};
export const MESSAGE_STATUSES = ['Received', 'Processing', 'Completed', 'Failed', 'Ignored'] as const;

export interface TelegramMessage {
	name: string;
	received_at: string;
	kind: MessageKind;
	text: string;
	sender_id: string;
	sender_name: string;
	status: string;
	reply_status: string;
	error: string;
	agent_run: string | null;
	agent: string | null;
}

export interface TelegramMessageDetail extends TelegramMessage {
	update_kind: string;
	chat_id: string;
	attachments: { kind: string; mime_type: string; filename: string; file_size: number }[];
	reply: { status: string; message_id: string | null; parts: { message_id: number }[]; error: string };
}

export interface MessageFilters { status?: string; kind?: MessageKind | ''; q?: string }

export interface AccessEntry {
	name: string;
	external_id: string;
	display_label?: string | null;
	entry_type: string;
	state: 'Pending' | 'Approved' | 'Revoked' | string;
	pairing_code?: string | null;
	approved_by?: string | null;
	creation: string;
}

export interface Binding {
	name: string;
	frappe_user: string;
	telegram_user_id: string;
	telegram_username?: string | null;
	role_scope: string;
	is_active: boolean;
	paired_at: string | null;
	last_seen_at: string | null;
}

export interface BusinessConnection {
	id: string;
	owner_id: string;
	owner_name: string;
	enabled: boolean;
	rights: Record<string, boolean>;
}

export interface SendTarget { chat_id: string; label: string; source: 'binding' | 'approved' }
export type SendKind = 'text' | 'photo' | 'document' | 'voice';

async function req<T>(verb: 'get' | 'post', method: string, args: Record<string, unknown>): Promise<Result<T>> {
	try {
		return unwrap<T>(await call[verb](`${BASE}.${method}`, args));
	} catch (e) {
		return { ok: false, error: getFrappeErrorMessage(e) };
	}
}

export const listMessages = (gateway: string, filters: MessageFilters, cursor?: string | null, limit = 25) =>
	req<{ success: boolean; items: TelegramMessage[]; next_cursor: string | null; has_more: boolean }>('get', 'list_messages', {
		gateway, filters: JSON.stringify(filters), limit, cursor: cursor ?? undefined,
	});
export const getMessage = (gateway: string, event: string) =>
	req<{ success: boolean; message: TelegramMessageDetail }>('get', 'get_message', { gateway, event });
export const listAccess = (gateway: string, state: string) => req<{ success: boolean; items: AccessEntry[] }>('get', 'list_access', { gateway, state });
export const approveAccess = (gateway: string, entry: string) => req<{ success: boolean }>('post', 'approve_access', { gateway, entry });
export const revokeAccess = (gateway: string, entry: string) => req<{ success: boolean }>('post', 'revoke_access', { gateway, entry });
export const listBindings = (gateway: string) => req<{ success: boolean; items: Binding[] }>('get', 'list_bindings', { gateway });
export const revokeBinding = (gateway: string, name: string) => req<{ success: boolean }>('post', 'revoke_binding', { gateway, name });
export const createBindingCodeForMe = (gateway: string, roleScope: string) =>
	req<{ success: boolean; code: string; expires_in: number; instructions: string }>('post', 'create_binding_code_for_me', { gateway, role_scope: roleScope });
export const listBusinessConnections = (gateway: string) => req<{ success: boolean; items: BusinessConnection[] }>('get', 'list_business_connections', { gateway });
export const listSendTargets = (gateway: string) => req<{ success: boolean; items: SendTarget[] }>('get', 'list_send_targets', { gateway });
export const sendTelegramMessage = (gateway: string, chatId: string, text: string, kind: SendKind, fileUrl?: string) =>
	req<{ success: boolean; message_ids: number[] }>('post', 'send_message', { gateway, chat_id: chatId, text, kind, file_url: fileUrl });

export async function uploadPrivateFile(f: File): Promise<Result<{ fileUrl: string }>> {
	try {
		const res = await file.uploadFile(f, { isPrivate: true });
		const fileUrl = (res as { data?: { message?: { file_url?: string } } })?.data?.message?.file_url;
		return fileUrl ? { ok: true, data: { fileUrl } } : { ok: false, error: 'The upload did not return a file.' };
	} catch (e) {
		return { ok: false, error: getFrappeErrorMessage(e) };
	}
}

// -- pure helpers ----------------------------------------------------------------------------------

const MAX_BYTES: Record<Exclude<SendKind, 'text'>, number> = { photo: 10 * 1024 * 1024, document: 50 * 1024 * 1024, voice: 20 * 1024 * 1024 };

/** Client-side pre-check of text and size limits only; file types are decided by the server alone (it reports `invalid_file`). */
export function validateSend(kind: SendKind, text: string, f: { size: number } | null): string {
	if (kind === 'text') {
		if (!text.trim()) return 'Write a message first.';
		return text.length > 4096 ? 'Text is limited to 4096 characters.' : '';
	}
	if (text.length > 1024) return 'Captions are limited to 1024 characters.';
	if (!f) return 'Attach a file.';
	if (f.size === 0) return 'The file is empty.';
	if (f.size > MAX_BYTES[kind]) return `The file is larger than ${MAX_BYTES[kind] / (1024 * 1024)} MB.`;
	return '';
}

export function statusTone(status: string): 'good' | 'bad' | 'neutral' {
	if (/^(completed|sent|delivered)$/i.test(status)) return 'good';
	if (/fail|error|dead/i.test(status)) return 'bad';
	return 'neutral';
}

export const RIGHT_LABEL: Record<string, string> = {
	can_reply: 'Reply', can_read_messages: 'Read messages', can_delete_sent_messages: 'Delete own messages',
	can_delete_all_messages: 'Delete all messages', can_edit_name: 'Edit name', can_manage_stories: 'Stories',
};
export const rightLabel = (key: string) => RIGHT_LABEL[key] ?? key.replace(/^can_/, '').replace(/_/g, ' ');
