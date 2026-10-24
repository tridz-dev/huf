import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

/** Typed client for the Telegram management page (huf/ai/telegram_management.py). No secrets cross this boundary. */
const BASE = 'huf.ai.telegram_management';

export type TelegramHealthState = 'healthy' | 'degraded' | 'blocked' | 'not_set_up' | 'disabled';
export type TelegramChecklistCode = 'bot_token' | 'webhook_secret' | 'webhook' | 'enabled' | 'first_message';

export interface TelegramChecklistItem {
	code: TelegramChecklistCode;
	state: 'done' | 'todo' | 'blocked';
}

/** pass: fine. fail: breaks the connection (moves health). warn: an optional feature needs a fix. off: not in use. */
export type TelegramCheckState = 'pass' | 'warn' | 'fail' | 'off';

export interface TelegramCheck {
	id: string;
	label: string;
	ok: boolean;
	state: TelegramCheckState;
	/** The exact fix; empty on pass and off rows. */
	hint: string;
}

export interface TelegramBot {
	id: number | null;
	username: string | null;
	can_join_groups: boolean;
	can_connect_to_business: boolean;
	supports_guest_queries: boolean;
	supports_join_request_queries: boolean;
	has_topics_enabled: boolean;
}

export type TelegramCapabilityFlag = Exclude<keyof TelegramBot, 'id' | 'username'>;

export interface TelegramOverview {
	name: string;
	enabled: boolean;
	webhook_url: string;
	token_present: boolean;
	webhook_secret_present: boolean;
	last_event_at: string | null;
	last_error: string | null;
	bot: TelegramBot | null;
	bot_error: string | null;
	typing?: TelegramTypingStatus | null;
}

/** Typing indicator counters (null when the gateway's typing indicator is off). Times are site-local strings. */
export interface TelegramTypingStatus {
	last_sent_at: string | null;
	sent_count_24h: number;
	last_error: string | null;
	last_error_at: string | null;
	keepalive_ticks: number;
}

export interface TelegramHealth {
	name: string;
	enabled: boolean;
	health: TelegramHealthState;
	checks: TelegramCheck[];
	checklist: TelegramChecklistItem[];
	pending_update_count: number | null;
	last_event_at: string | null;
	typing?: TelegramTypingStatus | null;
}

export interface TelegramGatewayOption {
	name: string;
	enabled: boolean;
	has_events: boolean;
}

export type Result<T> = { ok: true; data: T } | { ok: false; error: string };

type Envelope = { success?: boolean; error?: string; message?: string };

/** Unwrap the `{message: body}` envelope and turn `success: false` into an error result. */
export function unwrap<T>(res: unknown): Result<T> {
	const body = ((res && typeof res === 'object' && 'message' in res ? (res as { message: unknown }).message : res) ?? {}) as T & Envelope;
	if (body && body.success === false) return { ok: false, error: body.message || body.error || 'Request failed' };
	return { ok: true, data: body };
}

async function get<T>(method: string, args: Record<string, unknown>): Promise<Result<T>> {
	try {
		return unwrap<T>(await call.get(`${BASE}.${method}`, args));
	} catch (e) {
		return { ok: false, error: getFrappeErrorMessage(e) };
	}
}

export function listTelegramGateways() {
	return get<{ success: boolean; gateways: TelegramGatewayOption[] }>('list_telegram_gateways', {});
}

export function getTelegramOverview(gateway: string) {
	return get<{ success: boolean; gateway: TelegramOverview }>('get_telegram_overview', { gateway });
}

/** Live check against Telegram (bot token and webhook delivery). */
export function getTelegramHealth(gateway: string) {
	return get<{ success: boolean; gateway: TelegramHealth }>('get_telegram_health', { gateway });
}

const HEALTH_LABEL: Record<TelegramHealthState, string> = {
	healthy: 'Working',
	degraded: 'Needs attention',
	blocked: 'Blocked',
	not_set_up: 'Not set up yet',
	disabled: 'Turned off',
};

export function telegramHealthLabel(state: TelegramHealthState): string {
	return HEALTH_LABEL[state] ?? state;
}

export function checklistProgress(items: TelegramChecklistItem[]): { done: number; total: number } {
	return { done: items.filter((i) => i.state === 'done').length, total: items.length };
}

export interface Capability {
	flag: TelegramCapabilityFlag;
	title: string;
	help: string;
	on: boolean;
}

const CAPABILITY_COPY: Record<TelegramCapabilityFlag, { title: string; help: string }> = {
	can_join_groups: { title: 'Group chats', help: 'People can add this bot to groups and talk to it there.' },
	can_connect_to_business: { title: 'Business accounts', help: 'A Telegram Business account can connect this bot to answer customer chats for it.' },
	supports_guest_queries: { title: 'Guest questions', help: 'Anyone can ask the bot a question without starting a chat first.' },
	supports_join_request_queries: { title: 'Join requests', help: 'The bot can review people asking to join a group or channel.' },
	has_topics_enabled: { title: 'Topics', help: 'The bot can keep separate conversations in topics.' },
};

export const CAPABILITY_ORDER: TelegramCapabilityFlag[] = [
	'can_join_groups',
	'can_connect_to_business',
	'supports_guest_queries',
	'supports_join_request_queries',
	'has_topics_enabled',
];

/** Which Telegram modes the bot has, in display order, from the bot's reported flags. */
export function capabilityList(bot: TelegramBot | null): Capability[] {
	return CAPABILITY_ORDER.map((flag) => ({ flag, ...CAPABILITY_COPY[flag], on: Boolean(bot?.[flag]) }));
}

const CHECK_COPY: Record<string, string> = {
	bot_reachable: 'Telegram accepts the bot token.',
	webhook_info: 'Telegram could not be reached to read the connection.',
	webhook_url: 'Telegram is not sending messages to this site yet.',
	webhook_error: 'Telegram had trouble delivering recent messages.',
	webhook_pending: 'Messages are piling up and are not being picked up.',
	webhook_allowed_updates: 'The connection is missing some message types. Set it up again.',
	bot_identity: 'The bot has no username. Give it one in BotFather.',
};

/** Plain-language reading of a failed check; never the raw API wording. */
export function checkMessage(check: TelegramCheck): string {
	return CHECK_COPY[check.id] ?? 'Something needs your attention.';
}
