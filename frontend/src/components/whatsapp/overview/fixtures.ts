import type { GatewayHealthStatus } from '@/services/whatsappHealthApi';

export function gatewayFixture(over: Partial<GatewayHealthStatus> = {}): GatewayHealthStatus {
	return {
		name: 'GW-1',
		enabled: true,
		whatsapp_account: 'Acct-1',
		phone_number_id: '123',
		account_phone_mismatch: false,
		webhook_url: 'https://x.test/hook',
		health: 'healthy',
		reasons: [],
		next_step: null,
		checklist: [
			{ code: 'credentials', state: 'done' },
			{ code: 'app_secret', state: 'todo', action_url: '#app-secret' },
			{ code: 'test_message', state: 'todo', action_url: '#test-message' },
		],
		fallback_template: null,
		fallback_template_language: null,
		fallback_template_approved: null,
		last_event_at: new Date(Date.now() - 60_000).toISOString(),
		last_error: null,
		access_token_present: true,
		app_id_present: true,
		app_secret_present: true,
		verify_token_present: true,
		events_24h: { received: 3, failed: 0, unrouted: 0, rejected: 0 },
		last_failed_event: null,
		unrouted_phone_ids: [],
		policy: {},
		meta_links: { app_dashboard: null, whatsapp_manager: null, webhook_config: null },
		...over,
	};
}
