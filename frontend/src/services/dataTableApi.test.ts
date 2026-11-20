import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() }, db: {} }));
vi.mock('@/lib/frappe-error', () => ({
	handleFrappeError: (e: unknown) => {
		throw e;
	},
}));
import { call } from '@/lib/frappe-sdk';
import {
	bulkDeleteRows,
	bulkInsertRows,
	bulkUpdateRows,
	exportRows,
	getTableAgentActivity,
	getTableRecords,
	listTablesSummary,
	previewImport,
	restoreRows,
	runImport,
} from './dataTableApi';

const get = vi.mocked(call.get);
const post = vi.mocked(call.post);
const P = 'huf.huf.doctype.huf_data_table';
beforeEach(() => vi.clearAllMocks());

describe('dataTableApi', () => {
	it('getTableRecords sends filters/order and returns total', async () => {
		get.mockResolvedValue({ message: { items: [{ name: '1' }], hasMore: true, total: 9 } } as never);
		const r = await getTableRecords('DT', { filters: [['a', '=', 1]], orderBy: { field: 'a', order: 'asc' } });
		expect(r).toEqual({ items: [{ name: '1' }], hasMore: true, total: 9 });
		expect(get).toHaveBeenCalledWith(`${P}.api.get_table_records`, expect.objectContaining({
			filters: JSON.stringify([['a', '=', 1]]),
			order_by: 'a asc',
		}));
	});

	it('getTableRecords tolerates an older backend without total', async () => {
		get.mockResolvedValue({ message: { items: [], hasMore: false } } as never);
		expect((await getTableRecords('DT')).total).toBeUndefined();
	});

	it('mutations POST with JSON-encoded payloads', async () => {
		post.mockResolvedValue({ message: { ok: 1 } } as never);
		await bulkInsertRows('DT', [{ a: 1 }]);
		await bulkUpdateRows('DT', ['x'], { a: 2 });
		await bulkDeleteRows('DT', ['x']);
		await restoreRows('DT', ['x']);
		expect(post).toHaveBeenNthCalledWith(1, `${P}.rows.bulk_insert_rows`, { doctype_name: 'DT', rows: '[{"a":1}]' });
		expect(post).toHaveBeenNthCalledWith(2, `${P}.rows.bulk_update_rows`, { doctype_name: 'DT', names: '["x"]', values: '{"a":2}' });
		expect(post).toHaveBeenNthCalledWith(3, `${P}.rows.bulk_delete_rows`, { doctype_name: 'DT', names: '["x"]' });
		expect(post).toHaveBeenNthCalledWith(4, `${P}.rows.restore_rows`, { doctype_name: 'DT', names: '["x"]' });
	});

	it('import wrappers', async () => {
		post.mockResolvedValue({ message: {} } as never);
		await previewImport('T', '/f.csv');
		await runImport('T', '/f.csv', { mapping: { A: 'a' }, mode: 'update', keyField: 'a' });
		expect(post).toHaveBeenNthCalledWith(1, `${P}.import_export.preview_import`, { table_id: 'T', file_url: '/f.csv' });
		expect(post).toHaveBeenNthCalledWith(2, `${P}.import_export.run_import`, {
			table_id: 'T', file_url: '/f.csv', mapping: '{"A":"a"}', mode: 'update', key_field: 'a',
		});
	});

	it('read wrappers use GET', async () => {
		get.mockResolvedValue({ message: null } as never);
		expect(await listTablesSummary()).toEqual([]);
		expect(await getTableAgentActivity('T')).toEqual([]);
		expect(get).toHaveBeenCalledWith(`${P}.rows.get_table_agent_activity`, { table_id: 'T', limit: 20 });
		await exportRows('T', { names: ['a'] });
		expect(get).toHaveBeenLastCalledWith(`${P}.import_export.export_rows`, {
			table_id: 'T', filters: undefined, fields: undefined, names: '["a"]',
		});
	});
});
