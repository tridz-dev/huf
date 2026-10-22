import type { TelegramSettings, TelegramSettingValue, TelegramSettingValues } from '@/services/telegramSettingsApi';

/** Field layout, plain-language copy and dirty-tracking for the Telegram Settings tab. */

export type FieldKind = 'select' | 'switch' | 'number' | 'text' | 'template';

export interface FieldDef {
	name: string;
	label: string;
	help?: string;
	kind: FieldKind;
	/** Display names for stored option values; unknown values show as stored. */
	optionLabels?: Record<string, string>;
	/** Shown under the field while it is on (switches) or set to `warnValue` (selects). */
	warning?: string;
	warnValue?: string;
	/** Only show when another field has one of these values. */
	showWhen?: { field: string; equals: string };
	min?: number;
}

export interface SectionDef {
	id: 'replies' | 'access' | 'agent' | 'modes';
	title: string;
	description: string;
	fields: FieldDef[];
}

export const TEMPLATES_COMING_SOON = 'Templates coming soon';

export const SETTINGS_SECTIONS: SectionDef[] = [
	{
		id: 'replies',
		title: 'Replies',
		description: 'How the bot formats and sends its answers.',
		fields: [
			{
				name: 'telegram_parse_mode',
				label: 'Text format',
				kind: 'select',
				help: 'How bold, links and code in replies are shown.',
				optionLabels: { Plain: 'Plain text', HTML: 'Formatted (HTML)', MarkdownV2: 'Formatted (Markdown)' },
			},
			{
				name: 'preview_url',
				label: 'Link previews',
				kind: 'select',
				optionLabels: { 'Default (off)': 'Off (default)', On: 'On', Off: 'Off' },
			},
			{ name: 'telegram_silent_replies', label: 'Silent replies', kind: 'switch', help: 'Replies arrive without a notification sound.' },
			{
				name: 'telegram_protect_content',
				label: 'Protect content',
				kind: 'switch',
				help: 'People cannot forward or save what the bot sends.',
			},
			{
				name: 'voice_reply_mode',
				label: 'Voice note replies',
				kind: 'select',
				help: 'When someone sends a voice note, answer with a voice note.',
				optionLabels: { Off: 'Off', 'Voice only': 'Voice only', 'Text and voice': 'Text and voice' },
			},
			{ name: 'typing_indicator', label: 'Typing indicator', kind: 'switch', help: 'Show that the bot is typing while the agent works.' },
			{
				name: 'retry_max_attempts',
				label: 'Send attempts',
				kind: 'number',
				min: 1,
				help: 'How many times to try a reply that hits a temporary Telegram error.',
			},
		],
	},
	{
		id: 'access',
		title: 'Access',
		description: 'Who can talk to the bot and how new people get in.',
		fields: [
			{
				name: 'direct_policy',
				label: 'Direct messages',
				kind: 'select',
				optionLabels: {
					Disabled: 'Ignore everyone',
					Pairing: 'New people must pair first',
					'Allow list': 'Only approved people',
					Open: 'Anyone can message',
				},
				warning: 'Anyone on Telegram can start a conversation with your agent.',
				warnValue: 'Open',
			},
			{
				name: 'room_policy',
				label: 'Group chats',
				kind: 'select',
				optionLabels: { Disabled: 'Ignore groups', 'Allow list': 'Only approved groups', Open: 'Any group' },
			},
			{
				name: 'room_sender_policy',
				label: 'Who can talk in groups',
				kind: 'select',
				optionLabels: { 'Allow list': 'Only approved people', Open: 'Anyone in the group' },
			},
			{ name: 'mention_required', label: 'Mention required in groups', kind: 'switch', help: 'Only answer when the bot is mentioned or replied to.' },
			{
				name: 'pairing_ttl_minutes',
				label: 'Pairing request expires after (minutes)',
				kind: 'number',
				min: 1,
				showWhen: { field: 'direct_policy', equals: 'Pairing' },
			},
			{
				name: 'pairing_reply_enabled',
				label: 'Send the pairing code to new people',
				kind: 'switch',
				showWhen: { field: 'direct_policy', equals: 'Pairing' },
			},
			{
				name: 'pairing_pending_limit',
				label: 'Most waiting pairing requests',
				kind: 'number',
				min: 0,
				help: '0 turns the limit off.',
				showWhen: { field: 'direct_policy', equals: 'Pairing' },
			},
			{
				name: 'pairing_reply_daily_limit',
				label: 'Most pairing replies per day',
				kind: 'number',
				min: 0,
				help: '0 means no replies.',
				showWhen: { field: 'direct_policy', equals: 'Pairing' },
			},
			{
				name: 'telegram_bot_allowlist',
				label: 'Other bots allowed to talk to this bot',
				kind: 'text',
				help: 'Bot usernames, one per line or separated by commas. Leave empty to ignore other bots.',
			},
			{ name: 'telegram_bot_max_hops', label: 'Most bot-to-bot replies in a row', kind: 'number', min: 0, help: 'Stops two bots from answering each other forever.' },
			{ name: 'telegram_bot_rate_cap', label: 'Most bot messages per minute', kind: 'number', min: 0, help: '0 means no limit.' },
		],
	},
	{
		id: 'agent',
		title: 'Agent permissions',
		description: 'What your agents may do on their own, beyond answering the current chat.',
		fields: [
			{
				name: 'agent_recipient_scope',
				label: 'Who agents can message',
				kind: 'select',
				optionLabels: {
					'Current contact': 'Only the person in the chat',
					'Allow-list': 'The chat and an approved list',
					'Approved contacts': 'The chat and approved contacts',
					'Any number': 'Anyone',
				},
				warning: 'Agents can message any chat the bot can reach. Use this only for agents you trust.',
				warnValue: 'Any number',
			},
			{
				name: 'agent_recipient_allowlist',
				label: 'Approved chats',
				kind: 'text',
				help: 'Chat IDs or @usernames, one per line or separated by commas.',
				showWhen: { field: 'agent_recipient_scope', equals: 'Allow-list' },
			},
			{ name: 'agent_send_cap_per_run', label: 'Most messages per agent run', kind: 'number', min: 0, help: '0 means no limit.' },
			{ name: 'agent_send_cap_per_day', label: 'Most messages per day', kind: 'number', min: 0, help: '0 means no limit.' },
			{
				name: 'telegram_agent_allow_group_admin',
				label: 'Allow group admin actions',
				kind: 'switch',
				help: 'Agents can pin, ban, mute and manage members and topics where the bot is an admin.',
				warning: 'Agents can remove people and change groups. Turn this on only for agents you trust.',
			},
			{
				name: 'telegram_agent_allow_business',
				label: 'Allow business account actions',
				kind: 'switch',
				help: 'Agents can act in the Telegram Business chats connected to this bot.',
				warning: 'Agents can send messages from your business account.',
			},
			{
				name: 'telegram_agent_allow_profile',
				label: 'Allow bot profile changes',
				kind: 'switch',
				help: 'Agents can change the bot name, description, commands and menu button.',
				warning: 'Agents can change what people see on the bot profile.',
			},
		],
	},
	{
		id: 'modes',
		title: 'Modes',
		description: 'How the bot behaves for business chats, join requests and inline use.',
		fields: [
			{
				name: 'telegram_business_policy',
				label: 'Business chats',
				kind: 'select',
				optionLabels: {
					Ignore: 'Ignore',
					Observe: 'Read only',
					Draft: 'Draft replies for you to approve',
					Reply: 'Reply automatically',
				},
				warning: 'The agent answers your customers without you checking first.',
				warnValue: 'Reply',
			},
			{
				name: 'telegram_join_policy',
				label: 'Join requests',
				kind: 'select',
				optionLabels: { Queue: 'Hold for review', Decline: 'Decline', Agent: 'Let the agent decide' },
			},
			{ name: 'telegram_inline_enabled', label: 'Inline mode', kind: 'switch', help: 'People can use the bot from any chat by typing its name.' },
			{ name: 'telegram_streaming', label: 'Stream replies', kind: 'switch', help: 'Show the answer as it is written instead of all at once.' },
			{ name: 'telegram_default_template', label: 'Default template', kind: 'template' },
			{ name: 'telegram_welcome_template', label: 'Welcome template', kind: 'template', help: 'Sent when someone joins or starts the bot.' },
		],
	},
];

export type SettingsDraft = Record<string, TelegramSettingValue>;

/** Form values from the server: switches become booleans, numbers stay numbers. */
export function toDraft(settings: Pick<TelegramSettings, 'values'>): SettingsDraft {
	const draft: SettingsDraft = {};
	for (const section of SETTINGS_SECTIONS) {
		for (const f of section.fields) {
			if (!(f.name in settings.values)) continue;
			const v = settings.values[f.name];
			draft[f.name] = f.kind === 'switch' ? Boolean(v) : v;
		}
	}
	return draft;
}

/** Only the fields whose value differs from the saved one. */
export function dirtyValues(saved: SettingsDraft, draft: SettingsDraft): TelegramSettingValues {
	const out: TelegramSettingValues = {};
	for (const name of Object.keys(draft)) {
		if (name in saved && draft[name] !== saved[name]) out[name] = draft[name];
	}
	return out;
}

/** True when a number field was cleared or is below its minimum, so saving would be rejected. */
export function hasInvalidNumber(draft: SettingsDraft): boolean {
	for (const section of SETTINGS_SECTIONS) {
		for (const f of section.fields) {
			if (f.kind !== 'number' || !(f.name in draft)) continue;
			const v = draft[f.name];
			if (typeof v !== 'number' || Number.isNaN(v) || v < (f.min ?? 0)) return true;
		}
	}
	return false;
}

export function isVisible(field: FieldDef, draft: SettingsDraft): boolean {
	return !field.showWhen || draft[field.showWhen.field] === field.showWhen.equals;
}

/** The warning to show for a field in its current state, if any. */
export function activeWarning(field: FieldDef, value: TelegramSettingValue | undefined): string | null {
	if (!field.warning) return null;
	if (field.kind === 'switch') return value === true ? field.warning : null;
	return value === field.warnValue ? field.warning : null;
}
