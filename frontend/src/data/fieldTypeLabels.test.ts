import { describe, expect, it } from 'vitest';
import { FRIENDLY_TYPES, friendlyTypeName, toColumnType, typeGlyph } from './fieldTypeLabels';

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
		expect(toColumnType('Int')).toBe('number');
		expect(toColumnType('Currency')).toBe('currency');
		expect(toColumnType('Check')).toBe('checkbox');
		expect(toColumnType('Select')).toBe('select');
		expect(toColumnType('Link')).toBe('link');
		expect(toColumnType('Text')).toBe('longtext');
		expect(toColumnType('Datetime')).toBe('date');
		expect(toColumnType('Nope')).toBe('text');
	});
	it('has glyphs and unique picker labels', () => {
		expect(typeGlyph('Date')).toBeTruthy();
		expect(typeGlyph('Nope')).toBeTruthy();
		const labels = FRIENDLY_TYPES.map((t) => t.label);
		expect(new Set(labels).size).toBe(labels.length);
	});
});
