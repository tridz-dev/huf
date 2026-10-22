import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { unwrap, type Result } from './telegramApi';

/** Typed client for huf/ai/telegram_management_commands.py. No secrets cross this boundary. */
const BASE = 'huf.ai.telegram_management_commands';

export type CommandScope = 'default' | 'all_private_chats' | 'all_group_chats' | 'all_chat_administrators';
export const COMMAND_SCOPES: { value: CommandScope; label: string }[] = [
	{ value: 'default', label: 'Default (everyone)' },
	{ value: 'all_private_chats', label: 'Private chats' },
	{ value: 'all_group_chats', label: 'Group chats' },
	{ value: 'all_chat_administrators', label: 'Group admins' },
];

export interface BotCommand {
	command: string;
	description: string;
	is_ephemeral?: boolean;
}
export interface BotProfile {
	name: string;
	description: string;
	short_description: string;
}
export const PROFILE_LIMITS = { name: 64, short_description: 120, description: 512 } as const;
export const MAX_COMMANDS = 100;

export type MenuButtonType = 'commands' | 'web_app' | 'default';
export interface MenuButton {
	type: MenuButtonType;
	text?: string;
	web_app?: { url: string };
}

export interface TokenCheck {
	valid: boolean;
	id?: number | null;
	username?: string | null;
	first_name?: string | null;
	reason?: string;
}

export interface WebhookSummary {
	url: string;
	url_matches: boolean;
	pending_update_count: number;
	last_error_date: number | null;
	last_error_message: string;
	allowed_updates: string[] | null;
	allowed_updates_ok: boolean;
	expected_url: string;
	expected_allowed_updates: string[];
}

async function req<T>(verb: 'get' | 'post', method: string, args: Record<string, unknown>): Promise<Result<T>> {
	try {
		return unwrap<T>(await call[verb](`${BASE}.${method}`, args));
	} catch (e) {
		return { ok: false, error: getFrappeErrorMessage(e) };
	}
}

export const getBotProfile = (gateway: string, language = '') =>
	req<{ profile: BotProfile }>('get', 'get_bot_profile', { gateway, language });
export const setBotProfile = (gateway: string, fields: Partial<BotProfile>, language = '') =>
	req<{ updated: string[] }>('post', 'set_bot_profile', { gateway, language, ...fields });
export const getCommands = (gateway: string, scope: CommandScope, language = '') =>
	req<{ commands: BotCommand[] }>('get', 'get_commands', { gateway, scope, language });
export const setCommands = (gateway: string, scope: CommandScope, language: string, commands: BotCommand[]) =>
	req<{ count: number }>('post', 'set_commands', { gateway, scope, language, commands: JSON.stringify(commands) });
export const deleteCommands = (gateway: string, scope: CommandScope, language = '') =>
	req<object>('post', 'delete_commands', { gateway, scope, language });
export const getMenuButton = (gateway: string) => req<{ menu_button: MenuButton }>('get', 'get_menu_button', { gateway });
export const setMenuButton = (gateway: string, type: MenuButtonType, text = '', url = '') =>
	req<{ menu_button: MenuButton }>('post', 'set_menu_button', { gateway, type, text, url });
export const checkToken = (gateway: string) => req<{ check: TokenCheck }>('post', 'check_token', { gateway });
export const refreshWebhookHealth = (gateway: string) => req<{ webhook: WebhookSummary }>('get', 'refresh_webhook_health', { gateway });
/** Takes over delivery for the bot: the server refuses without confirm. */
export const setWebhookNow = (gateway: string, dropPending = false) =>
	req<{ webhook: WebhookSummary }>('post', 'set_webhook_now', { gateway, confirm: 1, drop_pending_updates: dropPending ? 1 : 0 });
export const deleteWebhookNow = (gateway: string, dropPending = false) =>
	req<{ webhook: WebhookSummary }>('post', 'delete_webhook_now', { gateway, confirm: 1, drop_pending_updates: dropPending ? 1 : 0 });

// -- validation helpers (mirror the server) ------------------------------------------------------

const NAME_RE = /^[a-z0-9_]{1,32}$/;

/** One error per row index (and a list-level error under key -1), empty when valid. */
export function validateCommands(rows: BotCommand[]): Record<number, string> {
	const errors: Record<number, string> = {};
	const seen = new Set<string>();
	if (rows.length > MAX_COMMANDS) errors[-1] = `At most ${MAX_COMMANDS} commands.`;
	rows.forEach((r, i) => {
		const name = r.command.trim();
		const desc = r.description.trim();
		if (!NAME_RE.test(name)) errors[i] = 'Name: 1-32 characters, lowercase letters, digits or underscore.';
		else if (seen.has(name)) errors[i] = 'Duplicate command.';
		else if (desc.length < 1 || desc.length > 256) errors[i] = 'Description: 1-256 characters.';
		seen.add(name);
	});
	return errors;
}

export function cleanCommands(rows: BotCommand[]): BotCommand[] {
	return rows.map((r) => {
		const c: BotCommand = { command: r.command.trim().replace(/^\//, ''), description: r.description.trim() };
		if (r.is_ephemeral) c.is_ephemeral = true;
		return c;
	});
}

export function validateProfile(p: BotProfile): Partial<Record<keyof BotProfile, string>> {
	const errors: Partial<Record<keyof BotProfile, string>> = {};
	if (!p.name.trim()) errors.name = 'Name cannot be empty.';
	(Object.keys(PROFILE_LIMITS) as (keyof typeof PROFILE_LIMITS)[]).forEach((k) => {
		if (p[k].length > PROFILE_LIMITS[k]) errors[k] = `At most ${PROFILE_LIMITS[k]} characters.`;
	});
	return errors;
}

export function validateMenuButton(type: MenuButtonType, text: string, url: string): string | null {
	if (type !== 'web_app') return null;
	if (!text.trim() || text.trim().length > 64) return 'Button text must be 1-64 characters.';
	if (!url.trim().startsWith('https://')) return 'The web app address must start with https://';
	return null;
}
