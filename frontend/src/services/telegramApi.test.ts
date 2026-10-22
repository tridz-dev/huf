import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() } }));
import { call } from '@/lib/frappe-sdk';
import {
	capabilityList,
	checkMessage,
	checklistProgress,
	getTelegramHealth,
	getTelegramOverview,
	listTelegramGateways,
	telegramHealthLabel,
	unwrap,
	type TelegramBot,
} from './telegramApi';

const get = vi.mocked(call.get);
beforeEach(() => vi.clearAllMocks());

describe('telegram api calls', () => {
	it('overview passes the gateway and unwraps the envelope', async () => {
		get.mockResolvedValue({ message: { success: true, gateway: { name: 'TG-1' } } } as never);
		const res = await getTelegramOverview('TG-1');
		expect(res).toEqual({ ok: true, data: { success: true, gateway: { name: 'TG-1' } } });
		expect(get).toHaveBeenCalledWith('huf.ai.telegram_management.get_telegram_overview', { gateway: 'TG-1' });
	});

	it('health and list use their own methods', async () => {
		get.mockResolvedValue({ message: { success: true } } as never);
		await getTelegramHealth('TG-1');
		await listTelegramGateways();
		expect(get).toHaveBeenNthCalledWith(1, 'huf.ai.telegram_management.get_telegram_health', { gateway: 'TG-1' });
		expect(get).toHaveBeenNthCalledWith(2, 'huf.ai.telegram_management.list_telegram_gateways', {});
	});

	it('maps success:false to an error, preferring the message', async () => {
		get.mockResolvedValue({ message: { success: false, error: 'not_found', message: 'Gateway not found.' } } as never);
		expect(await getTelegramHealth('x')).toEqual({ ok: false, error: 'Gateway not found.' });
		expect(unwrap({ message: { success: false } })).toEqual({ ok: false, error: 'Request failed' });
	});

	it('turns thrown errors into an error result', async () => {
		get.mockRejectedValue(new Error('network down'));
		expect((await getTelegramOverview('TG-1')).ok).toBe(false);
	});
});

describe('model helpers', () => {
	const bot: TelegramBot = {
		id: 1,
		username: 'b',
		can_join_groups: true,
		can_connect_to_business: false,
		supports_guest_queries: true,
		supports_join_request_queries: false,
		has_topics_enabled: false,
	};

	it('capabilityList follows the bot flags in a fixed order', () => {
		const list = capabilityList(bot);
		expect(list.map((c) => c.flag)).toEqual([
			'can_join_groups',
			'can_connect_to_business',
			'supports_guest_queries',
			'supports_join_request_queries',
			'has_topics_enabled',
		]);
		expect(list.filter((c) => c.on).map((c) => c.flag)).toEqual(['can_join_groups', 'supports_guest_queries']);
		expect(capabilityList(null).every((c) => !c.on)).toBe(true);
	});

	it('labels, progress and check copy', () => {
		expect(telegramHealthLabel('not_set_up')).toBe('Not set up yet');
		expect(checklistProgress([{ code: 'bot_token', state: 'done' }, { code: 'enabled', state: 'todo' }])).toEqual({ done: 1, total: 2 });
		expect(checkMessage({ id: 'webhook_url', label: '', ok: false, hint: 'getWebhookInfo failed' })).not.toMatch(/getWebhookInfo/);
		expect(checkMessage({ id: 'unknown', label: '', ok: false, hint: '' })).toBe('Something needs your attention.');
	});
});
