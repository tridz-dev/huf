// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { builderReducer, initialBuilderState } from './builderReducer';
import { needsDeleteConfirm, validateBuilder } from './fieldRules';
import { FieldDeleteConfirm } from './FieldDeleteConfirm';
import { FieldConfigPanel } from '../FieldConfigPanel';
import type { DataTableFieldDef, DataTableSchema } from '@/types/dataTable.types';

const schema = {
	name: 'T1', table_name: 'Customers',
	fields: [
		{ fieldname: 'company', fieldtype: 'Data', label: 'Company' },
		{ fieldname: 'status', fieldtype: 'Select', label: 'Status', options: 'A\nB' },
	],
} as unknown as DataTableSchema;

const loaded = () => builderReducer(initialBuilderState, { type: 'LOAD_SCHEMA', payload: schema });

describe('builder data-loss guards', () => {
	it('keeps the fieldname of a loaded field when its label changes', () => {
		const next = builderReducer(loaded(), {
			type: 'UPDATE_FIELD',
			payload: { index: 0, updates: { label: 'Organisation', fieldname: 'organisation' } },
		});
		expect(next.fields[0].label).toBe('Organisation');
		expect(next.fields[0].fieldname).toBe('company');
	});

	it('still lets a new field take its derived fieldname', () => {
		let s = loaded();
		s = builderReducer(s, { type: 'ADD_FIELD', payload: { fieldname: 'new_field', fieldtype: 'Data', label: '' } });
		s = builderReducer(s, { type: 'UPDATE_FIELD', payload: { index: 2, updates: { label: 'City', fieldname: 'city' } } });
		expect(s.fields[2].fieldname).toBe('city');
	});

	it('panel does not emit a fieldname for an existing field, and does for a new one', () => {
		const field: DataTableFieldDef = { fieldname: 'company', fieldtype: 'Data', label: 'Company' };
		const onUpdate = vi.fn();
		const { unmount } = render(<FieldConfigPanel field={field} isExisting onUpdate={onUpdate} onDelete={vi.fn()} onOpenTableSettings={vi.fn()} />);
		fireEvent.change(screen.getByLabelText(/Label/), { target: { value: 'Organisation' } });
		expect(onUpdate).toHaveBeenLastCalledWith({ label: 'Organisation' });
		unmount();
		const onUpdate2 = vi.fn();
		render(<FieldConfigPanel field={field} onUpdate={onUpdate2} onDelete={vi.fn()} onOpenTableSettings={vi.fn()} />);
		fireEvent.change(screen.getByLabelText(/Label/), { target: { value: 'Organisation' } });
		expect(onUpdate2).toHaveBeenLastCalledWith({ label: 'Organisation', fieldname: 'organisation' });
	});

	it('deleting an existing data field needs confirmation; a new one does not', () => {
		const s = loaded();
		expect(needsDeleteConfirm(s.fields[0], s.originalFields)).toBe(true);
		expect(needsDeleteConfirm({ fieldname: 'new_field', fieldtype: 'Data', label: '' }, s.originalFields)).toBe(false);
	});

	it('field delete confirm states the real row count and dependents', () => {
		const onConfirm = vi.fn();
		render(
			<FieldDeleteConfirm open onOpenChange={vi.fn()} fieldLabel="Company" recordCount={1284}
				dependents={[{ kind: 'Agent', label: 'Billing agent' }]} onConfirm={onConfirm} />
		);
		expect(screen.getByText(/1,284 rows/)).toBeTruthy();
		expect(screen.getByText('Billing agent')).toBeTruthy();
		expect(onConfirm).not.toHaveBeenCalled();
		fireEvent.click(screen.getByRole('button', { name: 'Delete field' }));
		expect(onConfirm).toHaveBeenCalled();
	});

	it('field delete confirm falls back to honest wording without a count', () => {
		render(<FieldDeleteConfirm open onOpenChange={vi.fn()} fieldLabel="Company" dependents={[]} onConfirm={vi.fn()} />);
		expect(screen.getByText(/column and its data/)).toBeTruthy();
	});

	it('blocks a dropdown with no options and a missing table name inline', () => {
		const e = validateBuilder('', [{ fieldname: 's', fieldtype: 'Select', label: 'S', options: ' \n' }]);
		expect(e.tableName).toBeTruthy();
		expect(e.fields[0].options).toBeTruthy();
	});
});
