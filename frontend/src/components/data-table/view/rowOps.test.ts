import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
	bulkDeleteRows: vi.fn(), bulkInsertRows: vi.fn(), bulkUpdateRows: vi.fn(),
	deleteTableRecord: vi.fn(), updateTableRecord: vi.fn(), createTableRecord: vi.fn(),
}));
vi.mock('@/services/dataTables/rowsApi', () => ({ bulkDeleteRows: m.bulkDeleteRows, bulkInsertRows: m.bulkInsertRows, bulkUpdateRows: m.bulkUpdateRows }));
vi.mock('@/services/dataTableApi', () => ({
	deleteTableRecord: m.deleteTableRecord, updateTableRecord: m.updateTableRecord, createTableRecord: m.createTableRecord,
	exportRows: vi.fn(), getTableRecords: vi.fn(),
}));

import { deleteMany, insertMany, isMissingEndpoint, updateMany } from './rowOps';

beforeEach(() => vi.clearAllMocks());

describe('rowOps fallback', () => {
	it('detects a missing endpoint only', () => {
		expect(isMissingEndpoint({ status: 404 })).toBe(true);
		expect(isMissingEndpoint(new Error('Failed to get method for command x'))).toBe(true);
		expect(isMissingEndpoint(new Error('Insufficient Permission'))).toBe(false);
		expect(isMissingEndpoint(new Error('Network error'))).toBe(false);
	});
	it('falls back per row when the endpoint is missing', async () => {
		m.bulkDeleteRows.mockRejectedValue({ status: 404 });
		expect(await deleteMany('D', ['a', 'b'])).toBe(false);
		expect(m.deleteTableRecord).toHaveBeenCalledTimes(2);
	});
	it('rethrows other errors without per-row calls', async () => {
		m.bulkDeleteRows.mockRejectedValue(new Error('Insufficient Permission'));
		await expect(deleteMany('D', ['a'])).rejects.toThrow('Permission');
		m.bulkUpdateRows.mockRejectedValue(new Error('Network error'));
		await expect(updateMany('D', ['a'], {})).rejects.toThrow('Network');
		m.bulkInsertRows.mockRejectedValue(new Error('Validation failed'));
		await expect(insertMany('D', [{}])).rejects.toThrow('Validation');
		expect(m.deleteTableRecord).not.toHaveBeenCalled();
		expect(m.updateTableRecord).not.toHaveBeenCalled();
		expect(m.createTableRecord).not.toHaveBeenCalled();
	});
});
