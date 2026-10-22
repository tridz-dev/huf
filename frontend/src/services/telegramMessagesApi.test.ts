import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() }, file: { uploadFile: vi.fn() } }));
import { call, file } from '@/lib/frappe-sdk';
import {
	createBindingCodeForMe, listMessages, rightLabel, sendTelegramMessage, statusTone, uploadPrivateFile, validateSend,
} from './telegramMessagesApi';

const get = vi.mocked(call.get);
const post = vi.mocked(call.post);
beforeEach(() => vi.clearAllMocks());

describe('telegram messages api', () => {
	it('list_messages serialises filters and cursor', async () => {
		get.mockResolvedValue({ message: { success: true, items: [], next_cursor: null, has_more: false } } as never);
		const res = await listMessages('TG-1', { kind: 'voice', status: 'Failed' }, 'abc', 10);
		expect(res.ok).toBe(true);
		expect(get).toHaveBeenCalledWith('huf.ai.telegram_management_messages.list_messages', {
			gateway: 'TG-1', filters: JSON.stringify({ kind: 'voice', status: 'Failed' }), limit: 10, cursor: 'abc',
		});
	});

	it('writes use POST and surface refusals', async () => {
		post.mockResolvedValue({ message: { success: false, error: 'recipient_not_permitted', message: 'Send only to an approved contact.' } } as never);
		expect(await sendTelegramMessage('TG-1', '99', 'hi', 'text')).toEqual({ ok: false, error: 'Send only to an approved contact.' });
		post.mockResolvedValue({ message: { success: true, code: 'HUF-1', expires_in: 600, instructions: 'go' } } as never);
		const res = await createBindingCodeForMe('TG-1', 'Viewer');
		expect(res.ok && res.data.code).toBe('HUF-1');
	});

	it('upload returns the file url or an error', async () => {
		vi.mocked(file.uploadFile).mockResolvedValue({ data: { message: { file_url: '/private/files/a.png' } } } as never);
		expect(await uploadPrivateFile(new File(['x'], 'a.png'))).toEqual({ ok: true, data: { fileUrl: '/private/files/a.png' } });
		vi.mocked(file.uploadFile).mockResolvedValue({} as never);
		expect((await uploadPrivateFile(new File(['x'], 'a.png'))).ok).toBe(false);
	});
});

describe('validateSend', () => {
	const f = (size: number, type: string) => ({ size, type, name: 'x' });
	it('checks text', () => {
		expect(validateSend('text', ' ', null)).toMatch(/Write/);
		expect(validateSend('text', 'x'.repeat(4097), null)).toMatch(/4096/);
		expect(validateSend('text', 'hi', null)).toBe('');
	});
	it('checks files', () => {
		expect(validateSend('photo', '', null)).toMatch(/Attach/);
		expect(validateSend('photo', '', f(11 * 1024 * 1024, 'image/png'))).toMatch(/10 MB/);
		expect(validateSend('photo', '', f(5, 'image/gif'))).toMatch(/must be/);
		expect(validateSend('photo', '', f(5, 'image/png'))).toBe('');
		expect(validateSend('document', '', f(5, 'application/pdf'))).toBe('');
		expect(validateSend('voice', '', f(5, 'audio/ogg'))).toBe('');
	});
});

describe('helpers', () => {
	it('status tone and right labels', () => {
		expect(statusTone('Completed')).toBe('good');
		expect(statusTone('Failed')).toBe('bad');
		expect(statusTone('Received')).toBe('neutral');
		expect(rightLabel('can_reply')).toBe('Reply');
		expect(rightLabel('can_do_thing')).toBe('do thing');
	});
});
