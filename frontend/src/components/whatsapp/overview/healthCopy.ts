import type { ChecklistCode, GatewayEvents24h, HealthReason, HealthState } from '@/services/whatsappHealthApi';

/** All user-facing strings for the WhatsApp health banner and setup checklist. */

export const BANNER_TITLE: Record<HealthState, string> = {
	healthy: 'Working: receiving and replying normally.',
	degraded: 'Needs attention',
	blocked: 'Blocked: this number cannot send or receive right now.',
	not_set_up: 'Finish setup to start receiving messages',
	disabled: 'This number is turned off',
};

export const BANNER_DISABLED_HELP = 'Messages sent to this number are ignored until you turn it on.';
export const BANNER_NOT_SET_UP_HELP = 'Complete the steps below and your agent will start answering WhatsApp messages.';
export const BANNER_TURN_ON = 'Turn on';
export const BANNER_CHECK_NOW = 'Check now';
export const BANNER_CHECKING = 'Checking…';
export const NO_MESSAGES_YET = 'No messages received yet';

export const CHECK_LABELS = {
	enabled: 'Enabled',
	credentials: 'Credentials',
	token: 'Token valid',
	tokenRejected: 'Token rejected',
	receiving: 'Receiving',
	delivering: 'Delivering',
} as const;

export const REASON_FALLBACK: Record<string, string> = {
	access_token_missing: 'Blocked: add the access token from Meta.',
	access_token_fix: 'Replace access token',
	access_token_invalid: 'Meta rejected the access token. It may have expired; replace it in Settings.',
	phone_number_id_missing: 'Blocked: add the phone number ID from Meta.',
	verify_token_missing: "Add the verify token so Meta can confirm this gateway's callback URL.",
	app_secret_missing: 'Add the app secret so we can confirm messages really come from Meta.',
	account_phone_mismatch: 'This number belongs to a different WhatsApp account than the one linked.',
	delivery_failures: 'Some replies are failing to send.',
	recent_error: 'The last message ran into an error.',
	fallback_template_unavailable: 'Replies after 24 hours will fail until the fallback template is approved.',
	voice_reply_ffmpeg_missing: 'Voice replies are on but ffmpeg is missing, so replies go out as text.',
	senders_waiting: "People are waiting for approval. Your agent won't reply to them until you approve them.",
	no_events_yet:
		"Meta hasn't sent us anything yet. Check the callback URL and that the messages field is subscribed.",
};

/** Credentials step when Meta rejected the saved token: same wording and action as the banner. */
export const CREDENTIALS_REPLACE_COPY = {
	title: 'Replace access token',
	help: 'Meta rejected the saved token. Paste a new one.',
	action: 'Replace access token',
};

export function degradedFallback(failed: number): string {
	return `Replies are failing: ${failed} in the last 24 hours.`;
}

/** Backend message when present, otherwise friendly copy for the reason code. */
export function reasonMessage(reason: HealthReason | undefined, events: GatewayEvents24h): string {
	if (reason?.message) return reason.message;
	if (reason && REASON_FALLBACK[reason.code]) return REASON_FALLBACK[reason.code];
	return events.failed > 0 ? degradedFallback(events.failed) : 'Something needs your attention.';
}

export const CHECKLIST_COPY: Record<ChecklistCode, { title: string; help: string; action: string }> = {
	meta_app: {
		title: 'Create a Meta app',
		help: 'Add the WhatsApp product to a Meta developer app.',
		action: 'Open Meta',
	},
	credentials: {
		title: 'Add your credentials',
		help: 'Paste the phone number ID, business account ID, app ID, access token and app secret from Meta.',
		action: 'Add credentials',
	},
	webhook: {
		title: 'Set the callback URL',
		help: 'Paste the callback URL and verify token into your Meta app.',
		action: 'Open webhook settings',
	},
	subscribed: {
		title: 'Subscribe to messages',
		help: 'Turn on the messages field so Meta sends us incoming messages.',
		action: 'Open webhook settings',
	},
	app_secret: {
		title: 'Add the app secret',
		help: 'We use it to confirm messages really come from Meta.',
		action: 'Add app secret',
	},
	enabled: {
		title: 'Turn the number on',
		help: 'Switch this number on so your agent starts replying.',
		action: 'Turn on',
	},
	approve_sender: {
		title: 'Approve your first sender',
		help: "New people get a pairing code. Your agent replies once you approve them.",
		action: 'Review requests',
	},
	test_message: {
		title: 'Send a test message',
		help: 'Message the number from your own phone and wait for a reply.',
		action: 'Open WhatsApp',
	},
};

export const CHECKLIST_COMPLETE = 'Setup complete';
export const CHECKLIST_ALL_DONE = 'All steps done';
export const CHECKLIST_SHOW = 'Show steps';
export const CHECKLIST_HIDE = 'Hide steps';

export function stepsLeft(left: number, total: number): string {
	return `${left} of ${total} steps left`;
}
