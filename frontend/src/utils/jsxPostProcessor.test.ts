import { describe, expect, it } from 'vitest';
import { fixCommonJsxMistakes } from './jsxPostProcessor';

describe('fixCommonJsxMistakes', () => {
	it('wraps bare template-like array entries in backticks', () => {
		const input =
			'<Tooltip formatter={(value) => [AED ${value}, "Amount"]} />';
		const output = fixCommonJsxMistakes(input);

		expect(output).toBe(
			'<Tooltip formatter={(value) => [`AED ${value}`, "Amount"]} />'
		);
	});

	it('fixes key attributes missing template literal backticks', () => {
		const input = '<Cell key={cell-${idx}} fill="#888" />';
		const output = fixCommonJsxMistakes(input);

		expect(output).toBe('<Cell key={`cell-${idx}`} fill="#888" />');
	});

	it('inserts || before hex color fallback strings', () => {
		const input = 'fill={colors[entry.status]  "#8884d8"}';
		const output = fixCommonJsxMistakes(input);

		expect(output).toBe('fill={colors[entry.status] || "#8884d8"}');
	});

	it('leaves valid JSX unchanged', () => {
		const input =
			'<Tooltip formatter={(value) => [`AED ${value}`, "Amount"]} />';
		expect(fixCommonJsxMistakes(input)).toBe(input);
	});
});
