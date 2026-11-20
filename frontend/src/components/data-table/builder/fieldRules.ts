import { LAYOUT_FIELD_TYPES } from '@/data/fieldTypes';
import type { DataTableFieldDef } from '@/types/dataTable.types';

const RESERVED = new Set([
	'name', 'doctype', 'owner', 'creation', 'modified',
	'modified_by', 'docstatus', 'idx', 'parent', 'parentfield', 'parenttype',
]);

/**
 * Derive a fieldname from a label. ONLY for fields created in this session:
 * the fieldname of a field that already exists in the database is the column
 * name, so changing it would orphan the column and its data.
 */
export function deriveFieldname(label: string, taken: ReadonlySet<string>, fallback: string): string {
	let name = label
		.toLowerCase()
		.replace(/[^a-z0-9\s]/g, '')
		.replace(/\s+/g, '_')
		.replace(/_+/g, '_')
		.replace(/^_|_$/g, '');
	if (!name) return fallback;
	if (RESERVED.has(name)) name = `${name}_field`;
	let candidate = name;
	for (let i = 2; taken.has(candidate); i++) candidate = `${name}_${i}`;
	return candidate;
}

/** Fieldname -> fieldtype for fields as loaded from the server. */
export type OriginalFields = Readonly<Record<string, string>>;

export function isExistingField(field: DataTableFieldDef, original: OriginalFields): boolean {
	return Object.prototype.hasOwnProperty.call(original, field.fieldname);
}

/** Deleting an existing data field removes a column with data; layout fields hold none. */
export function needsDeleteConfirm(field: DataTableFieldDef, original: OriginalFields): boolean {
	return isExistingField(field, original) && !LAYOUT_FIELD_TYPES.includes(field.fieldtype);
}

export interface FieldErrors { label?: string; options?: string }
export interface BuilderErrors {
	tableName?: string;
	noFields?: string;
	fields: Record<number, FieldErrors>;
	firstFieldIndex: number | null;
	count: number;
}

export function validateBuilder(tableName: string, fields: DataTableFieldDef[]): BuilderErrors {
	const out: BuilderErrors = { fields: {}, firstFieldIndex: null, count: 0 };
	if (!tableName.trim()) { out.tableName = 'Give the table a name.'; out.count++; }
	let dataFields = 0;
	fields.forEach((f, i) => {
		if (LAYOUT_FIELD_TYPES.includes(f.fieldtype)) return;
		dataFields++;
		const e: FieldErrors = {};
		if (!f.label?.trim()) e.label = 'Give this field a name.';
		if (f.fieldtype === 'Select' && !(f.options ?? '').split('\n').some((o) => o.trim())) {
			e.options = 'Add at least one option, or pick another type.';
		}
		if (e.label || e.options) {
			out.fields[i] = e;
			out.count++;
			if (out.firstFieldIndex === null) out.firstFieldIndex = i;
		}
	});
	if (dataFields === 0) { out.noFields = 'Add at least one field.'; out.count++; }
	return out;
}
