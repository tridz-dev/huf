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

/** Leading exception class of a Frappe error (createFrappeError.exceptionType can carry the message tail). */
function excName(v: unknown): string {
	if (typeof v !== 'string') return '';
	return (v.split('.').pop() ?? '').match(/^[A-Za-z_]\w*/)?.[0] ?? '';
}

/**
 * True when the error means the bulk endpoint itself doesn't exist. Decided only on the exception type
 * (the frappe error helpers expose no HTTP status): AttributeError, or Frappe's "Failed to get method"
 * signature. A DoesNotExistError ("<Doctype> <name> not found") is a missing record, never a missing endpoint.
 */
export function isMissingEndpoint(err: unknown): boolean {
	const e = err as { message?: unknown; exc_type?: unknown; exception?: unknown; exceptionType?: unknown; originalError?: unknown } | null;
	if (!e || typeof e !== 'object') return false;
	const types = [e.exceptionType, e.exc_type, e.exception].map(excName);
	if (types.includes('DoesNotExistError')) {
		const text = [e.message, e.exception].filter((x) => typeof x === 'string').join(' ');
		if (!/failed to get method/i.test(text)) return false;
	}
	if (types.includes('AttributeError')) return true;
	const text = [e.message, e.exception].filter((x) => typeof x === 'string').join(' ');
	if (/failed to get method/i.test(text)) return true;
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

export const SELECT_ALL_CAP = 5000;

export async function fetchNames(doctype: string, filters: TableRecordFilter[], search: string, total: number): Promise<string[]> {
	const r = await getTableRecords(doctype, {
		fields: ['name'],
		limit: Math.min(total, SELECT_ALL_CAP),
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
