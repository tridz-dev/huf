import { describe, expect, it } from 'vitest';
import { FRIENDLY_TYPES, friendlyTypeName, gridColumnType, typeGlyph } from './fieldTypeLabels';

describe('fieldTypeLabels', () => {
	it('maps friendly names', () => {
		expect(friendlyTypeName('Data')).toBe('Text');
		expect(friendlyTypeName('Small Text')).toBe('Long text');
		expect(friendlyTypeName('Long Text')).toBe('Long text');
		expect(friendlyTypeName('Int')).toBe('Whole number');
		expect(friendlyTypeName('Float')).toBe('Number');
		expect(friendlyTypeName('Datetime')).toBe('Date and time');
		expect(friendlyTypeName('Link')).toBe('Link to table');
		expect(friendlyTypeName('Attach Image')).toBe('Image');
		expect(friendlyTypeName('Weird')).toBe('Weird');
	});
	it('maps grid types', () => {
		expect(gridColumnType('Int')).toBe('number');
		expect(gridColumnType('Check')).toBe('check');
		expect(gridColumnType('Select')).toBe('select');
		expect(gridColumnType('Link')).toBe('link');
		expect(gridColumnType('Text')).toBe('longtext');
		expect(gridColumnType('Datetime')).toBe('date');
		expect(gridColumnType('Nope')).toBe('text');
	});
	it('has glyphs and unique picker labels', () => {
		expect(typeGlyph('Date')).toBeTruthy();
		expect(typeGlyph('Nope')).toBeTruthy();
		const labels = FRIENDLY_TYPES.map((t) => t.label);
		expect(new Set(labels).size).toBe(labels.length);
	});
});
