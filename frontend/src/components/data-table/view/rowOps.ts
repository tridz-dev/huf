import type { CellValue } from '@/components/grid';
import {
	createTableRecord,
	deleteTableRecord,
	exportRows,
	getTableRecords,
	updateTableRecord,
} from '@/services/dataTableApi';
import { bulkDeleteRows, bulkInsertRows, bulkUpdateRows } from '@/services/dataTables/rowsApi';
import type { ExportRowsResult, TableRecordFilter } from '@/types/dataTable.types';
import { toApiValue, toApiValues } from './model';

/** Bulk endpoints first; per-row calls when the server doesn't have them yet. */

export async function updateMany(doctype: string, names: string[], values: Record<string, CellValue>): Promise<void> {
	const api = toApiValues(values);
	try {
		await bulkUpdateRows(doctype, names, api);
	} catch {
		await Promise.all(names.map((n) => updateTableRecord(doctype, n, api)));
	}
}

export async function insertMany(doctype: string, rows: Record<string, CellValue>[]): Promise<string[]> {
	const api = rows.map(toApiValues);
	try {
		const r = await bulkInsertRows(doctype, api);
		return (r.errors ?? []).map((e) => `Row ${e.index + 1}: ${e.message}`);
	} catch {
		const errors: string[] = [];
		for (const [i, row] of api.entries()) {
			try {
				await createTableRecord(doctype, row);
			} catch (err) {
				errors.push(`Row ${i + 1}: ${err instanceof Error ? err.message : 'could not be added'}`);
			}
		}
		return errors;
	}
}

/** Returns true when the rows can be restored (the bulk endpoint handled it). */
export async function deleteMany(doctype: string, names: string[]): Promise<boolean> {
	try {
		await bulkDeleteRows(doctype, names);
		return true;
	} catch {
		for (const n of names) await deleteTableRecord(doctype, n);
		return false;
	}
}

export async function setOne(doctype: string, name: string, key: string, value: CellValue): Promise<void> {
	await updateTableRecord(doctype, name, { [key]: toApiValue(value) });
}

export async function fetchNames(doctype: string, filters: TableRecordFilter[], search: string, total: number): Promise<string[]> {
	const r = await getTableRecords(doctype, {
		fields: ['name'],
		limit: Math.min(total, 5000),
		filters: filters.length ? filters : undefined,
		search: search || undefined,
	});
	return r.items.map((i) => String(i.name));
}

/** Server CSV, or null when the endpoint isn't available. */
export async function serverExport(
	tableId: string,
	params: { filters?: TableRecordFilter[]; names?: string[] },
): Promise<ExportRowsResult | null> {
	try {
		const r = await exportRows(tableId, params);
		return r && typeof r.content === 'string' ? r : null;
	} catch {
		return null;
	}
}
