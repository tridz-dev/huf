// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { DataTableSchema } from '@/types/dataTable.types';

const api = vi.hoisted(() => ({
	getTableRecords: vi.fn(),
	createTableRecord: vi.fn(),
	updateTableRecord: vi.fn(),
	deleteTableRecord: vi.fn(),
	exportRows: vi.fn(),
	bulkDeleteRows: vi.fn(),
	bulkUpdateRows: vi.fn(),
	bulkInsertRows: vi.fn(),
	restoreRows: vi.fn(),
	toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));
vi.mock('@/services/dataTableApi', () => ({
	getTableRecords: api.getTableRecords, createTableRecord: api.createTableRecord,
	updateTableRecord: api.updateTableRecord, deleteTableRecord: api.deleteTableRecord, exportRows: api.exportRows,
}));
vi.mock('@/services/dataTables/rowsApi', () => ({
	bulkDeleteRows: api.bulkDeleteRows, bulkUpdateRows: api.bulkUpdateRows, bulkInsertRows: api.bulkInsertRows, restoreRows: api.restoreRows,
}));
vi.mock('sonner', () => ({ toast: api.toast }));

import { DataTab } from './DataTab';

const schema = {
	name: 't', table_name: 'Customers', doctype_name: 'HT Customers', description: '', icon: '', autoname_method: '', title_field_name: 'company',
	fields: [
		{ fieldname: 'company', fieldtype: 'Data', label: 'Company' },
		{ fieldname: 'seats', fieldtype: 'Int', label: 'Seats' },
	],
} as unknown as DataTableSchema;

const items = Array.from({ length: 25 }, (_, i) => ({ name: `R${i}`, company: `Co ${i}`, seats: i }));

describe('DataTab', () => {
	beforeEach(() => {
		api.getTableRecords.mockResolvedValue({ items, hasMore: true, total: 1284 });
	});
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('shows the server total and pages by 25', async () => {
		render(<DataTab schema={schema} tableId="t" onImport={() => undefined} />);
		await screen.findByText('Co 0');
		expect(screen.getByText('Showing 1–25 of 1,284 rows')).toBeInTheDocument();
		fireEvent.click(screen.getByRole('button', { name: 'Next' }));
		await waitFor(() => expect(api.getTableRecords).toHaveBeenLastCalledWith('HT Customers', expect.objectContaining({ limit: 25, start: 25 })));
	});

	it('passes filters to the server and shows a chip', async () => {
		render(<DataTab schema={schema} tableId="t" onImport={() => undefined} />);
		await screen.findByText('Co 0');
		fireEvent.click(screen.getByRole('button', { name: /Filter/ }));
		fireEvent.change(await screen.findByLabelText('Value'), { target: { value: 'ac' } });
		fireEvent.click(screen.getByRole('button', { name: 'Add filter' }));
		await waitFor(() =>
			expect(api.getTableRecords).toHaveBeenCalledWith('HT Customers', expect.objectContaining({ filters: [['company', '=', 'ac']], start: 0 })),
		);
		expect(screen.getByTestId('filter-chip')).toBeInTheDocument();
	});

	it('falls back to hasMore wording when total is missing', async () => {
		api.getTableRecords.mockResolvedValue({ items, hasMore: true, total: undefined });
		render(<DataTab schema={schema} tableId="t" onImport={() => undefined} />);
		await screen.findByText('Co 0');
		expect(screen.getByText('Rows 1–25, more available')).toBeInTheDocument();
	});

	it('shows the empty state with add and import', async () => {
		api.getTableRecords.mockResolvedValue({ items: [], hasMore: false, total: 0 });
		const onImport = vi.fn();
		render(<DataTab schema={schema} tableId="t" onImport={onImport} />);
		fireEvent.click(await screen.findByRole('button', { name: /Import/ }));
		expect(onImport).toHaveBeenCalled();
	});
});
