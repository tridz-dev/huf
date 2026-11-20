// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ImportDialog } from './ImportDialog';
import type { DataTableSchema } from '@/types/dataTable.types';

const svc = vi.hoisted(() => ({
	previewImport: vi.fn(),
	runImport: vi.fn(),
	getImportJobStatus: vi.fn(),
	isQueuedImport: (r: any) => r?.queued === true,
	startTableBulkImport: vi.fn(),
	getTableBulkImportStatus: vi.fn(),
}));
vi.mock('@/services/dataTableApi', () => svc);
vi.mock('@/lib/frappe-sdk', () => ({
	file: { uploadFile: vi.fn().mockResolvedValue({ data: { message: { file_url: '/private/f.csv' } } }) },
}));

const schema = {
	name: 'T1', table_name: 'Customers', fields: [
		{ fieldname: 'company', fieldtype: 'Data', label: 'Company' },
	],
} as unknown as DataTableSchema;

const preview = {
	columns: [{ header: 'Company', detected_type: 'Data', mapped_field: 'company', issues: 0 }],
	sample_rows: [['Acme']], total_rows: 3, valid_rows: 2,
	invalid_rows: [{ row: 3, message: 'bad' }],
};

async function pickFile() {
	render(<ImportDialog open onOpenChange={() => {}} schema={schema} />);
	const input = document.querySelector('input[type="file"]') as HTMLInputElement;
	fireEvent.change(input, { target: { files: [new File(['a'], 'a.csv')] } });
}

describe('ImportDialog', () => {
	beforeEach(() => vi.clearAllMocks());

	it('previews then imports valid rows', async () => {
		svc.previewImport.mockResolvedValue(preview);
		svc.runImport.mockResolvedValue({ inserted: 2, updated: 0, rejected: 1, rejected_rows: [], rejected_csv: 'x' });
		const done = vi.fn();
		render(<ImportDialog open onOpenChange={() => {}} schema={schema} onImported={done} />);
		fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [new File(['a'], 'a.csv')] } });
		fireEvent.click(await screen.findByRole('button', { name: /Import 2 valid rows/ }));
		await screen.findByTestId('import-summary');
		expect(svc.runImport).toHaveBeenCalledWith('T1', '/private/f.csv', expect.objectContaining({ mode: 'insert' }));
		expect(done).toHaveBeenCalled();
	});

	it('requires explicit confirm for replace', async () => {
		svc.previewImport.mockResolvedValue(preview);
		await pickFile();
		fireEvent.click(await screen.findByLabelText(/Replace all rows/));
		const btn = screen.getByRole('button', { name: /Import 2 valid rows/ }) as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
		fireEvent.click(screen.getByLabelText(/Delete all existing rows/));
		await waitFor(() => expect(btn.disabled).toBe(false));
	});

	it('shows a newer-server message when the endpoint is absent', async () => {
		svc.previewImport.mockRejectedValue(new Error('Method huf...preview_import not found'));
		await pickFile();
		expect(await screen.findByText(/needs a newer server/)).toBeTruthy();
	});
});
