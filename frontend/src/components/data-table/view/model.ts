import type { CellValue, ColumnType, GridColumn } from '@/components/grid';
import { parseCell } from '@/components/grid';
import { LAYOUT_FIELD_TYPES } from '@/data/fieldTypes';
import { toColumnType } from '@/data/fieldTypeLabels';
import type { DataTableFieldDef, DataTableSchema, TableRecordFilter } from '@/types/dataTable.types';

export type Row = Record<string, CellValue> & { name: string };

export const PAGE_SIZE = 25;
export const DRAFT_PREFIX = '__draft__';

export function isDraft(id: string): boolean {
	return id.startsWith(DRAFT_PREFIX);
}

export function dataFields(schema: DataTableSchema): DataTableFieldDef[] {
	return schema.fields.filter((f) => !LAYOUT_FIELD_TYPES.includes(f.fieldtype));
}

export function buildColumns(schema: DataTableSchema): GridColumn<Row>[] {
	const fields = dataFields(schema);
	const title = schema.title_field_name || fields[0]?.fieldname;
	return fields.map((f) => {
		const type = toColumnType(f.fieldtype);
		const col: GridColumn<Row> = {
			key: f.fieldname,
			label: f.label || f.fieldname,
			type,
			required: !!f.reqd,
			readOnly: !!f.read_only,
			tag: f.fieldname === title ? 'title' : undefined,
			width: type === 'longtext' ? 'lg' : type === 'checkbox' ? 'sm' : 'md',
		};
		if (type === 'select') {
			col.options = (f.options ?? '')
				.split('\n')
				.map((o) => o.trim())
				.filter(Boolean)
				.map((value) => ({ value }));
		}
		return col;
	});
}

/** Server record to grid row. Checkbox values arrive as 0/1. */
export function toRow(record: Record<string, unknown>, columns: GridColumn<Row>[]): Row {
	const row: Row = { name: String(record.name ?? '') };
	for (const c of columns) {
		const v = record[c.key];
		if (c.type === 'checkbox') row[c.key] = !!v && v !== '0';
		else if (v === null || v === undefined) row[c.key] = null;
		else if (typeof v === 'object') row[c.key] = JSON.stringify(v);
		else row[c.key] = v as CellValue;
	}
	return row;
}

/** Grid value to what the API stores. */
export function toApiValue(value: CellValue): unknown {
	if (typeof value === 'boolean') return value ? 1 : 0;
	return value === undefined ? null : value;
}

export function toApiValues(values: Record<string, CellValue>): Record<string, unknown> {
	return Object.fromEntries(Object.entries(values).map(([k, v]) => [k, toApiValue(v)]));
}

export function defaultsFor(schema: DataTableSchema): Record<string, unknown> {
	const out: Record<string, unknown> = {};
	for (const f of dataFields(schema)) {
		if (f.default !== undefined && f.default !== '') out[f.fieldname] = f.default;
	}
	return out;
}

/** Required fields with no default: a new row can't be saved until they're filled. */
export function requiredWithoutDefault(schema: DataTableSchema): string[] {
	return dataFields(schema).filter((f) => f.reqd && (f.default === undefined || f.default === '')).map((f) => f.fieldname);
}

export function isBlank(v: CellValue): boolean {
	return v === null || v === undefined || v === '';
}

// ─── Filters and sort ───

export type FilterOp = 'is' | 'is not' | 'contains' | 'does not contain' | 'is more than' | 'is less than' | 'is at least' | 'is at most' | 'is before' | 'is after' | 'is empty' | 'is not empty';

export interface FilterCond {
	field: string;
	op: FilterOp;
	value: string;
}

const TEXT_OPS: FilterOp[] = ['is', 'is not', 'contains', 'does not contain', 'is empty', 'is not empty'];
const NUM_OPS: FilterOp[] = ['is', 'is not', 'is more than', 'is less than', 'is at least', 'is at most', 'is empty', 'is not empty'];
const DATE_OPS: FilterOp[] = ['is', 'is not', 'is before', 'is after', 'is empty', 'is not empty'];

export function opsFor(type: ColumnType): FilterOp[] {
	if (type === 'number' || type === 'currency') return NUM_OPS;
	if (type === 'date') return DATE_OPS;
	if (type === 'checkbox') return ['is'];
	if (type === 'select') return ['is', 'is not', 'is empty', 'is not empty'];
	return TEXT_OPS;
}

export const needsValue = (op: FilterOp) => op !== 'is empty' && op !== 'is not empty';

const OP_API: Record<Exclude<FilterOp, 'contains' | 'does not contain' | 'is empty' | 'is not empty'>, string> = {
	is: '=',
	'is not': '!=',
	'is more than': '>',
	'is less than': '<',
	'is at least': '>=',
	'is at most': '<=',
	'is before': '<',
	'is after': '>',
};

export function toApiFilters(conds: FilterCond[], columns: GridColumn<Row>[]): TableRecordFilter[] {
	const out: TableRecordFilter[] = [];
	for (const c of conds) {
		const col = columns.find((x) => x.key === c.field);
		if (c.op === 'is empty') out.push([c.field, 'is', 'not set']);
		else if (c.op === 'is not empty') out.push([c.field, 'is', 'set']);
		else if (c.op === 'contains') out.push([c.field, 'like', `%${c.value}%`]);
		else if (c.op === 'does not contain') out.push([c.field, 'not like', `%${c.value}%`]);
		else {
			let v: unknown = c.value;
			if (col?.type === 'checkbox') v = c.value === 'Yes' || c.value === 'true' ? 1 : 0;
			else if (col && (col.type === 'number' || col.type === 'currency')) v = Number(c.value);
			out.push([c.field, OP_API[c.op], v]);
		}
	}
	return out;
}

export function describeValue(cond: FilterCond): string | undefined {
	return needsValue(cond.op) ? cond.value : undefined;
}

export function sortWords(type: ColumnType | undefined, direction: 'asc' | 'desc'): string {
	if (type === 'date') return direction === 'asc' ? 'Oldest first' : 'Newest first';
	if (type === 'number' || type === 'currency') return direction === 'asc' ? '1→9' : '9→1';
	return direction === 'asc' ? 'A→Z' : 'Z→A';
}

// ─── Paste and export ───

export interface PasteResult {
	updates: Array<{ name: string; values: Record<string, CellValue> }>;
	inserts: Array<Record<string, CellValue>>;
	errors: string[];
}

/** Map a pasted matrix onto rows starting at a cell: existing rows update, extra rows insert. */
export function planPaste(
	matrix: string[][],
	at: { rowId: string | null; key: string },
	rows: Row[],
	columns: GridColumn<Row>[],
): PasteResult {
	const startCol = Math.max(0, columns.findIndex((c) => c.key === at.key));
	const startRow = at.rowId ? rows.findIndex((r) => r.name === at.rowId) : -1;
	const plan: PasteResult = { updates: [], inserts: [], errors: [] };
	matrix.forEach((cells, i) => {
		const values: Record<string, CellValue> = {};
		cells.forEach((text, j) => {
			const col = columns[startCol + j];
			if (!col || col.readOnly) return;
			if (col.type === 'checkbox') {
				values[col.key] = /^(yes|true|1|y)$/i.test(text.trim());
				return;
			}
			const parsed = parseCell(col.type, text);
			if ('error' in parsed) plan.errors.push(`Row ${i + 1}, ${col.label}: ${parsed.error}`);
			else values[col.key] = parsed.value;
		});
		const target = startRow >= 0 ? rows[startRow + i] : undefined;
		if (target && !isDraft(target.name)) plan.updates.push({ name: target.name, values });
		else if (Object.keys(values).length) plan.inserts.push(values);
	});
	return plan;
}

export function toTsv(rows: Row[], columns: GridColumn<Row>[]): string {
	return rows.map((r) => columns.map((c) => String(r[c.key] ?? '')).join('\t')).join('\n');
}

function csvCell(v: unknown): string {
	const s = v === null || v === undefined ? '' : String(v);
	return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Client-side CSV, used when the export endpoint isn't available. */
export function toCsv(rows: Row[], columns: GridColumn<Row>[]): string {
	const head = columns.map((c) => csvCell(c.label)).join(',');
	return [head, ...rows.map((r) => columns.map((c) => csvCell(r[c.key])).join(','))].join('\n');
}

export function downloadCsv(filename: string, content: string): void {
	const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8' }));
	const a = document.createElement('a');
	a.href = url;
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	a.remove();
	URL.revokeObjectURL(url);
}

export function errorText(err: unknown, fallback = 'Something went wrong'): string {
	return err instanceof Error && err.message ? err.message : fallback;
}
