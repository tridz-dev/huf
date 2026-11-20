import { describe, expect, it } from 'vitest';
import type { DataTableSchema } from '@/types/dataTable.types';
import { buildColumns, planPaste, requiredWithoutDefault, toApiFilters, toCsv, toRow, type Row } from './model';

const schema = {
	name: 't', table_name: 'T', doctype_name: 'HT', description: '', icon: '', autoname_method: '', title_field_name: 'company',
	fields: [
		{ fieldname: 'sec', fieldtype: 'Section Break', label: 'S' },
		{ fieldname: 'company', fieldtype: 'Data', label: 'Company', reqd: 1 },
		{ fieldname: 'seats', fieldtype: 'Int', label: 'Seats' },
		{ fieldname: 'stage', fieldtype: 'Select', label: 'Stage', options: 'New\nWon', in_list_view: 0 },
		{ fieldname: 'paid', fieldtype: 'Check', label: 'Paid' },
	],
} as unknown as DataTableSchema;

describe('table view model', () => {
	const cols = buildColumns(schema);
	it('builds typed columns for all non-layout fields', () => {
		expect(cols.map((c) => [c.key, c.type])).toEqual([['company', 'text'], ['seats', 'number'], ['stage', 'select'], ['paid', 'checkbox']]);
		expect(cols[0].tag).toBe('title');
		expect(cols[2].options?.map((o) => o.value)).toEqual(['New', 'Won']);
		expect(requiredWithoutDefault(schema)).toEqual(['company']);
	});
	it('maps filters to API triples', () => {
		expect(toApiFilters([
			{ field: 'company', op: 'contains', value: 'ac' },
			{ field: 'seats', op: 'is at least', value: '5' },
			{ field: 'stage', op: 'is empty', value: '' },
			{ field: 'paid', op: 'is', value: 'Yes' },
		], cols)).toEqual([['company', 'like', '%ac%'], ['seats', '>=', 5], ['stage', 'is', 'not set'], ['paid', '=', 1]]);
	});
	it('plans paste into updates then inserts', () => {
		const rows: Row[] = [toRow({ name: 'A', company: 'a' }, cols), toRow({ name: 'B', company: 'b' }, cols)];
		const plan = planPaste([['x', '1'], ['y', '2'], ['z', 'nope']], { rowId: 'B', key: 'company' }, rows, cols);
		expect(plan.updates).toEqual([{ name: 'B', values: { company: 'x', seats: 1 } }]);
		expect(plan.inserts).toEqual([{ company: 'y', seats: 2 }, { company: 'z' }]);
		expect(plan.errors).toHaveLength(1);
	});
	it('quotes CSV cells', () => {
		expect(toCsv([toRow({ name: 'A', company: 'a,"b"' }, cols)], cols.slice(0, 1))).toBe('Company\n"a,""b"""');
	});
});
