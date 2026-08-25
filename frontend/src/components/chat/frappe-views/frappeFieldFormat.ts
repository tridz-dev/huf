/**
 * Shared cell/label formatting helpers for the frappe-list and
 * frappe-report artifact views. Kept separate from the two view components
 * since both need the exact same "how do I render this fieldtype" logic.
 */

import type { FrappeFieldMeta } from '@/types/artifact.types';

/** Fieldtypes that are pure layout in Desk and never carry a value - the
 * same set frappe_generic.py already strips out of `meta.fields` server
 * side, kept here too in case a caller passes raw doctype meta through. */
const LAYOUT_FIELDTYPES = new Set(['Section Break', 'Column Break', 'Tab Break', 'HTML', 'Button']);

export function isDisplayField(field: FrappeFieldMeta): boolean {
	return !LAYOUT_FIELDTYPES.has(field.fieldtype);
}

/** Render one cell value for a list/report table column, based on the
 * field's Frappe fieldtype. Link fields are rendered as plain text (the
 * value is just the linked doctype's name) - following the target
 * doctype is a follow-up, not required here. */
export function formatFrappeCellValue(value: unknown, field: FrappeFieldMeta): string {
	if (value === null || value === undefined || value === '') {
		return '-';
	}

	switch (field.fieldtype) {
		case 'Check':
			return value ? 'Yes' : 'No';
		case 'Currency':
		case 'Float':
			return typeof value === 'number' ? value.toFixed(2) : String(value);
		case 'Percent':
			return `${value}%`;
		case 'Date':
		case 'Datetime': {
			const d = new Date(String(value));
			return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
		}
		case 'Link':
		case 'Dynamic Link':
			// Text only - the value is the linked doc's name, not a live link.
			return String(value);
		default:
			return String(value);
	}
}
