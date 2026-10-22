import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() } }));
import { call } from '@/lib/frappe-sdk';
import {
	checkToken,
	cleanCommands,
	deleteWebhookNow,
	getCommands,
	setCommands,
	setWebhookNow,
	validateCommands,
	validateMenuButton,
	validateProfile,
} from './telegramCommandsApi';

const get = vi.mocked(call.get);
const post = vi.mocked(call.post);
beforeEach(() => vi.clearAllMocks());

describe('telegramCommandsApi calls', () => {
	it('get_commands uses GET with scope and language', async () => {
		get.mockResolvedValue({ message: { success: true, commands: [] } } as never);
		await getCommands('G', 'all_private_chats', 'en');
		expect(get).toHaveBeenCalledWith('huf.ai.telegram_management_commands.get_commands', { gateway: 'G', scope: 'all_private_chats', language: 'en' });
	});

	it('set_commands posts JSON commands', async () => {
		post.mockResolvedValue({ message: { success: true, count: 1 } } as never);
		await setCommands('G', 'default', '', [{ command: 'help', description: 'Help' }]);
		expect(post.mock.calls[0][1]).toMatchObject({ gateway: 'G', commands: '[{"command":"help","description":"Help"}]' });
	});

	it('webhook mutations always send confirm=1', async () => {
		post.mockResolvedValue({ message: { success: true } } as never);
		await setWebhookNow('G', true);
		await deleteWebhookNow('G');
		expect(post).toHaveBeenNthCalledWith(1, 'huf.ai.telegram_management_commands.set_webhook_now', { gateway: 'G', confirm: 1, drop_pending_updates: 1 });
		expect(post).toHaveBeenNthCalledWith(2, 'huf.ai.telegram_management_commands.delete_webhook_now', { gateway: 'G', confirm: 1, drop_pending_updates: 0 });
	});

	it('maps server errors and thrown errors to results', async () => {
		post.mockResolvedValue({ message: { success: false, error: 'invalid', message: 'Bad' } } as never);
		expect(await checkToken('G')).toEqual({ ok: false, error: 'Bad' });
		post.mockRejectedValue(new Error('down'));
		expect((await checkToken('G')).ok).toBe(false);
	});
});

describe('validation helpers', () => {
	it('flags bad names, duplicates and descriptions per row', () => {
		const e = validateCommands([
			{ command: 'ok', description: 'Fine' },
			{ command: 'Bad Name', description: 'x' },
			{ command: 'ok', description: 'dup' },
			{ command: 'empty', description: ' ' },
		]);
		expect(e[0]).toBeUndefined();
		expect(e[1]).toMatch(/Name/);
		expect(e[2]).toBe('Duplicate command.');
		expect(e[3]).toMatch(/Description/);
	});

	it('cleanCommands trims, strips slash, keeps ephemeral only when set', () => {
		expect(cleanCommands([{ command: ' /help ', description: ' Help ', is_ephemeral: true }, { command: 'a', description: 'b', is_ephemeral: false }])).toEqual([
			{ command: 'help', description: 'Help', is_ephemeral: true },
			{ command: 'a', description: 'b' },
		]);
	});

	it('profile limits', () => {
		expect(validateProfile({ name: 'n', description: '', short_description: '' })).toEqual({});
		const e = validateProfile({ name: '', description: 'x'.repeat(513), short_description: 'x'.repeat(121) });
		expect(Object.keys(e).sort()).toEqual(['description', 'name', 'short_description']);
	});

	it('menu button needs https text/url only for web_app', () => {
		expect(validateMenuButton('commands', '', '')).toBeNull();
		expect(validateMenuButton('web_app', 'Open', 'http://x')).toMatch(/https/);
		expect(validateMenuButton('web_app', '', 'https://x')).toMatch(/text/);
		expect(validateMenuButton('web_app', 'Open', 'https://x')).toBeNull();
	});
});
