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

/** Bulk endpoints first; per-row calls only when the server doesn't have them yet. */

/** True when the error means the bulk endpoint itself doesn't exist (not a permission/validation/network failure). */
export function isMissingEndpoint(err: unknown): boolean {
	const e = err as { message?: unknown; status?: unknown; httpStatus?: unknown; exc_type?: unknown; exceptionType?: unknown; originalError?: unknown } | null;
	if (!e) return false;
	if (e.status === 404 || e.httpStatus === 404) return true;
	if (e.exc_type === 'AttributeError' || e.exceptionType === 'AttributeError') return true;
	const msg = typeof e.message === 'string' ? e.message : '';
	if (/\b404\b|not found|failed to get method|has no attribute|no such method/i.test(msg) && !/permission/i.test(msg)) return true;
	return e.originalError ? isMissingEndpoint(e.originalError) : false;
}

export async function updateMany(doctype: string, names: string[], values: Record<string, CellValue>): Promise<void> {
	const api = toApiValues(values);
	try {
		await bulkUpdateRows(doctype, names, api);
	} catch (err) {
		if (!isMissingEndpoint(err)) throw err;
		await Promise.all(names.map((n) => updateTableRecord(doctype, n, api)));
	}
}

export async function insertMany(doctype: string, rows: Record<string, CellValue>[]): Promise<string[]> {
	const api = rows.map(toApiValues);
	try {
		const r = await bulkInsertRows(doctype, api);
		return (r.errors ?? []).map((e) => `Row ${e.index + 1}: ${e.message}`);
	} catch (err) {
		if (!isMissingEndpoint(err)) throw err;
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
	} catch (err) {
		if (!isMissingEndpoint(err)) throw err;
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
