import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() }, file: { uploadFile: vi.fn() } }));
import { call, file } from '@/lib/frappe-sdk';
import {
	deleteTemplate, detectVariables, draftToValues, emptyDraft, filterTemplates, listTemplates, problemsByField, rowToDraft,
	saveTemplate, sendTestTemplate, syncVariables, uploadTemplateMedia, validateDraft, type TemplateSummary,
} from './telegramTemplatesApi';

const get = vi.mocked(call.get);
const post = vi.mocked(call.post);
beforeEach(() => vi.clearAllMocks());

describe('variables', () => {
	it('detects unique names in order, across texts', () => {
		expect(detectVariables('Hi {{ name }} {{order_id}} {{name}}', '{"u":"{{link}}"}')).toEqual(['name', 'order_id', 'link']);
		expect(detectVariables('{{1bad}} {{ok}}')).toEqual(['ok']);
	});
	it('syncVariables keeps typed values and drops unused rows', () => {
		const rows = [{ variable: 'name', default_value: 'x', example: 'Sam' }, { variable: 'gone', default_value: '', example: '' }];
		expect(syncVariables(rows, 'Hi {{name}} {{new}}', '')).toEqual([rows[0], { variable: 'new', default_value: '', example: '' }]);
	});
});

describe('draft mapping', () => {
	it('rowToDraft normalises server data', () => {
		const d = rowToDraft({ name: 'a', template_name: 'a', is_active: 0, parse_mode: 'Bogus' as never, variables: [{ variable: 'v' }] });
		expect(d.is_active).toBe(false);
		expect(d.parse_mode).toBe('HTML');
		expect(d.variables).toEqual([{ variable: 'v', default_value: '', example: '' }]);
	});
	it('draftToValues nulls empties and drops media when none', () => {
		const v = draftToValues({ ...emptyDraft('G'), template_name: ' hi ', media: '/f.png', body: 'x' });
		expect(v).toMatchObject({ template_name: 'hi', gateway: 'G', media: null, buttons_json: null, is_active: 1, description: null });
	});
});

describe('validateDraft', () => {
	const fields = (p: ReturnType<typeof validateDraft>) => p.map((x) => x.field);
	it('requires name and body', () => {
		expect(fields(validateDraft(emptyDraft()))).toEqual(['template_name', 'body']);
	});
	it('media needs a file; caption limit; bad json', () => {
		const d = { ...emptyDraft(), template_name: 'a', body: 'x'.repeat(1025), media_type: 'photo' as const, buttons_json: '[1]' };
		expect(fields(validateDraft(d))).toEqual(['media', 'body', 'buttons_json']);
		expect(validateDraft({ ...d, media: '/f.png', body: 'ok', buttons_json: '' })).toEqual([]);
	});
	it('problemsByField collapses variables.N', () => {
		expect(problemsByField([{ field: 'variables.2', message: 'm' }, { field: 'body', message: 'b' }])).toEqual({ variables: 'm', body: 'b' });
	});
});

describe('api calls', () => {
	it('list maps the envelope', async () => {
		get.mockResolvedValue({ message: { success: true, templates: [{ name: 'a' }] } } as never);
		expect(await listTemplates('G')).toEqual({ ok: true, data: [{ name: 'a' }] });
		expect(get).toHaveBeenCalledWith('huf.ai.telegram_management_templates.list_templates', { gateway: 'G' });
	});
	it('save returns field problems', async () => {
		post.mockResolvedValue({ message: { success: false, error: 'invalid', message: 'bad', problems: [{ field: 'body', message: 'bad' }] } } as never);
		expect(await saveTemplate(emptyDraft())).toEqual({ ok: false, error: 'bad', problems: [{ field: 'body', message: 'bad' }] });
	});
	it('save sends name only when updating', async () => {
		post.mockResolvedValue({ message: { success: true, template: { name: 'a', template_name: 'a' } } } as never);
		await saveTemplate({ ...emptyDraft(), name: 'a' });
		expect(post.mock.calls[0][1]).toMatchObject({ name: 'a' });
		await saveTemplate(emptyDraft());
		expect(post.mock.calls[1][1]).not.toHaveProperty('name');
	});
	it('delete and send-test use POST; send-test always confirms', async () => {
		post.mockResolvedValue({ message: { success: true } } as never);
		await deleteTemplate('a');
		await sendTestTemplate({ gateway: 'G', chatId: ' 42 ', name: 'a', variables: { x: '1' } });
		expect(post).toHaveBeenNthCalledWith(1, 'huf.ai.telegram_management_templates.delete_template', { name: 'a' });
		expect(post.mock.calls[1][1]).toEqual({ gateway: 'G', chat_id: '42', name: 'a', variables: { x: '1' }, confirm: 1 });
	});
	it('send-test surfaces the refusal text', async () => {
		post.mockResolvedValue({ message: { success: false, error: 'chat_not_allowed', message: 'nope' } } as never);
		expect(await sendTestTemplate({ gateway: 'G', chatId: '1', name: 'a', variables: {} })).toEqual({ ok: false, error: 'nope' });
	});
	it('upload returns the file url', async () => {
		vi.mocked(file.uploadFile).mockResolvedValue({ data: { message: { file_url: '/files/a.png' } } } as never);
		expect(await uploadTemplateMedia(new File(['x'], 'a.png'))).toEqual({ ok: true, data: { fileUrl: '/files/a.png' } });
	});
});

it('filterTemplates searches name and description', () => {
	const rows = [{ template_name: 'Welcome', description: 'new users', language: 'en' }, { template_name: 'Bye', description: null, language: 'de' }] as TemplateSummary[];
	expect(filterTemplates(rows, 'users')).toHaveLength(1);
	expect(filterTemplates(rows, '')).toHaveLength(2);
});

describe('SDK method binding', () => {
	it('calls call.get and call.post as methods (the SDK needs `this`)', async () => {
		get.mockResolvedValue({ message: { ok: true, data: [] } } as never);
		post.mockResolvedValue({ message: { ok: true, data: {} } } as never);
		await listTemplates('TG Parity');
		await deleteTemplate('tg_welcome_demo');
		expect(get.mock.contexts[0]).toBe(call);
		expect(post.mock.contexts[0]).toBe(call);
	});
});
