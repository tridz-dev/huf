import type { TelegramChecklistCode, TelegramHealthState } from '@/services/telegramApi';

/** All user-facing strings for the Telegram health banner and setup checklist. */

export const BANNER_TITLE: Record<TelegramHealthState, string> = {
	healthy: 'Working: receiving and replying normally.',
	degraded: 'Needs attention',
	blocked: 'Blocked: this bot cannot send or receive right now.',
	not_set_up: 'Finish setup to start receiving messages',
	disabled: 'This bot is turned off',
};

export const BANNER_DISABLED_HELP = 'Messages sent to this bot are ignored until you turn it on.';
export const BANNER_NOT_SET_UP_HELP = 'Complete the steps below and your agent will start answering Telegram messages.';
export const BANNER_TURN_ON = 'Turn on';
export const BANNER_CHECK_NOW = 'Check now';
export const BANNER_CHECKING = 'Checking…';
export const NO_MESSAGES_YET = 'No messages received yet';

export const CHECKLIST_COMPLETE = 'Setup complete';
export const CHECKLIST_ALL_DONE = 'All steps done';
export const CHECKLIST_SHOW = 'Show steps';
export const CHECKLIST_HIDE = 'Hide steps';

export function stepsLeft(left: number, total: number): string {
	return `${left} of ${total} steps left`;
}

export const CHECKLIST_COPY: Record<TelegramChecklistCode, { title: string; help: string; action: string }> = {
	bot_token: { title: 'Add your bot token', help: 'Create a bot with BotFather in Telegram and paste its token.', action: 'Open BotFather' },
	webhook_secret: { title: 'Add a webhook secret', help: 'A private phrase that proves messages really come from Telegram.', action: 'Add secret' },
	webhook: { title: 'Connect Telegram to this site', help: 'Telegram needs to know where to send new messages.', action: 'Open settings' },
	enabled: { title: 'Turn the bot on', help: 'Switch the gateway on so your agent starts answering.', action: 'Turn on' },
	first_message: { title: 'Send a test message', help: 'Message your bot in Telegram to confirm it answers.', action: 'Open settings' },
};

export const CHECK_PILLS = {
	enabled: 'Enabled',
	token: 'Token accepted',
	tokenRejected: 'Token rejected',
	connected: 'Connected',
	receiving: 'Receiving',
} as const;
