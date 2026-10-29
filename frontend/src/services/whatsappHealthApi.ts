import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

/**
 * Typed client for the WhatsApp Overview/Settings page: per-gateway health,
 * setup checklist and the token check. The backend (whatsapp/health.py,
 * whatsapp/token_check.py) is built in parallel; this file is the agreed
 * contract. Reconcile field names with the backend's final report if they differ.
 */
const BASE = 'huf.ai.whatsapp.management';

export type HealthState = 'healthy' | 'degraded' | 'blocked' | 'not_set_up' | 'disabled';
export type HealthSeverity = 'error' | 'warning';

export interface HealthReason {
	code: string;
	severity: HealthSeverity;
	message: string;
}

export type ChecklistCode =
	| 'meta_app'
	| 'credentials'
	| 'webhook'
	| 'subscribed'
	| 'app_secret'
	| 'enabled'
	| 'approve_sender'
	| 'test_message';

export interface ChecklistItem {
	code: ChecklistCode;
	state: 'done' | 'todo' | 'blocked';
	action_url?: string | null;
}

export interface NextStep {
	code: string;
	label: string;
	action_url?: string | null;
}

export interface GatewayPolicy {
	direct_policy?: string | null;
	room_policy?: string | null;
	room_sender_policy?: string | null;
	mention_required?: boolean;
	pairing_enabled?: boolean;
	default_target?: { type: string; name: string } | null;
}

export interface GatewayEvents24h {
	received: number;
	failed: number;
	unrouted: number;
	rejected: number;
}

export interface LastFailedEvent {
	name: string;
	at: string;
	error: string | null;
}

export interface MetaLinks {
	app_dashboard: string | null;
	whatsapp_manager: string | null;
	webhook_config: string | null;
}

export interface TokenCheckSummary {
	valid: boolean;
	token_type: string | null;
	expires_at: string | null; // ISO, null = never expires
	missing_scopes: string[];
	waba_ids: string[];
	phone: { display?: string | null; verified_name?: string | null; quality?: string | null; tier?: string | null } | null;
	webhook_subscribed: boolean | null;
	checked_at: string | null;
	source: 'debug_token' | 'phone_number' | null;
	error_code?: string | number | null;
	message?: string | null;
}

export interface GatewayHealthStatus {
	name: string;
	enabled: boolean;
	whatsapp_account: string | null;
	phone_number_id: string | null;
	account_phone_mismatch: boolean;
	webhook_url: string;
	/** The channel credential this gateway uses ('' when none is connected). */
	integration_settings?: string;
	health: HealthState;
	/** PLAN 4.1 stage: not_connected, connected_unverified, receiving, live_unrouted, live, blocked, degraded or off. */
	setup_stage?: string | null;
	reasons: HealthReason[];
	next_step: NextStep | null;
	checklist: ChecklistItem[];
	fallback_template: string | null;
	fallback_template_language: string | null;
	fallback_template_approved: boolean | null;
	last_event_at: string | null;
	last_error: string | null;
	access_token_present: boolean;
	app_id_present: boolean;
	app_secret_present: boolean;
	verify_token_present: boolean;
	events_24h: GatewayEvents24h;
	last_failed_event: LastFailedEvent | null;
	unrouted_phone_ids: string[];
	policy: GatewayPolicy;
	meta_links: MetaLinks;
	/** The last token check: the server's cached result, replaced by a live check made on this page. */
	token_check?: TokenCheckSummary | null;
}

export interface WhatsAppAccountSummary {
	name: string;
	phone_id?: string | null;
	status?: string | null;
}

export interface SetupStatusResponse {
	success: boolean;
	connector_available: boolean;
	accounts?: WhatsAppAccountSummary[]; // the gateway's own account (empty without the connector)
	gateway?: GatewayHealthStatus; // when gateway_name was given
	gateways?: { name: string; health: HealthState; enabled: boolean }[]; // site summary (switcher dots)
	error?: string;
	message?: string;
}

export type CheckTokenResponse = { success: boolean; error?: string } & Partial<TokenCheckSummary>;

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

async function get<T>(method: string, args: Record<string, unknown>): Promise<Result<T>> {
	try {
		const res = await call.get(`${BASE}.${method}`, args);
		const body = ((res && typeof res === 'object' && 'message' in res ? (res as { message: unknown }).message : res) ?? {}) as T & {
			success?: boolean;
			error?: string;
			message?: string;
		};
		if (body && body.success === false) return { ok: false, error: body.message || body.error || 'Request failed' };
		return { ok: true, data: body };
	} catch (e) {
		return { ok: false, error: getFrappeErrorMessage(e) };
	}
}

async function post<T>(method: string, args: Record<string, unknown>): Promise<Result<T>> {
	try {
		const res = await call.post(`${BASE}.${method}`, args);
		const body = ((res && typeof res === 'object' && 'message' in res ? (res as { message: unknown }).message : res) ?? {}) as T & {
			success?: boolean;
			error?: string;
			message?: string;
		};
		if (body && body.success === false) return { ok: false, error: body.message || body.error || 'Request failed' };
		return { ok: true, data: body };
	} catch (e) {
		return { ok: false, error: getFrappeErrorMessage(e) };
	}
}

/** Health, checklist and connection details for one gateway (or the site summary when omitted). */
export function getSetupStatus(gatewayName?: string) {
	return get<SetupStatusResponse>('get_setup_status', gatewayName ? { gateway_name: gatewayName } : {});
}

/** Live check of the access token, phone number and webhook subscription (admin only, rate limited). */
export function checkToken(gatewayName: string) {
	return post<CheckTokenResponse>('check_token', { gateway_name: gatewayName });
}

const HEALTH_LABEL: Record<HealthState, string> = {
	healthy: 'Working',
	degraded: 'Needs attention',
	blocked: 'Blocked',
	not_set_up: 'Not set up yet',
	disabled: 'Turned off',
};

export function healthLabel(state: HealthState): string {
	return HEALTH_LABEL[state] ?? state;
}

export function checklistProgress(items: ChecklistItem[]): { done: number; total: number } {
	return { done: items.filter((i) => i.state === 'done').length, total: items.length };
}
