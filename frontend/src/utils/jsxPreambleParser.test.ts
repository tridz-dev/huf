import { describe, expect, it } from 'vitest';
import { extractJsxAndBindings, splitPreambleAndJsx, stripJsxComments } from './jsxPreambleParser';

const EXPENSE_PREAMBLE = `const data = [
  { employee: "HR-EMP-00050", amount: 560, status: "Draft" },
  { employee: "HR-EMP-00002", amount: 180, status: "Unpaid" },
  { employee: "HR-EMP-00013", amount: 55, status: "Unpaid" }
];

const colors = { Draft: "#FF9900", Unpaid: "#007BFF" };

`;

const EXPENSE_JSX = `<Card>
  <CardHeader>
    <CardTitle>Expense Claims by Employee</CardTitle>
  </CardHeader>
  <CardContent>
    <BarChart data={data}>
      <Bar dataKey="amount" />
    </BarChart>
  </CardContent>
</Card>`;

describe('splitPreambleAndJsx', () => {
	it('splits const declarations from JSX', () => {
		const { preamble, jsx } = splitPreambleAndJsx(EXPENSE_PREAMBLE + EXPENSE_JSX);

		expect(preamble).toContain('const data = [');
		expect(preamble).toContain('const colors = {');
		expect(jsx).toMatch(/^<Card>/);
	});

	it('returns pure JSX when there is no preamble', () => {
		const { preamble, jsx } = splitPreambleAndJsx(EXPENSE_JSX);

		expect(preamble).toBe('');
		expect(jsx).toBe(EXPENSE_JSX);
	});
});

describe('extractJsxAndBindings', () => {
	it('extracts data and colors bindings from chart preamble', () => {
		const result = extractJsxAndBindings(EXPENSE_PREAMBLE + EXPENSE_JSX);

		expect(result.warnings).toEqual([]);
		expect(result.jsx).toMatch(/^<Card>/);
		expect(result.bindings.data).toEqual([
			{ employee: 'HR-EMP-00050', amount: 560, status: 'Draft' },
			{ employee: 'HR-EMP-00002', amount: 180, status: 'Unpaid' },
			{ employee: 'HR-EMP-00013', amount: 55, status: 'Unpaid' },
		]);
		expect(result.bindings.colors).toEqual({
			Draft: '#FF9900',
			Unpaid: '#007BFF',
		});
	});

	it('falls back to raw JSX when preamble is invalid', () => {
		const source = 'const bad = fetch("x");\n<div />';
		const result = extractJsxAndBindings(source);

		expect(result.bindings).toEqual({});
		expect(result.warnings.length).toBeGreaterThan(0);
		expect(result.jsx).toBe(source);
	});

	it('supports member access on extracted bindings', () => {
		const source = `const colors = { Draft: "#FF9900" };
const draftColor = colors.Draft;
<div style={{ color: draftColor }} />`;

		const result = extractJsxAndBindings(source);

		expect(result.bindings.draftColor).toBe('#FF9900');
		expect(result.jsx).toMatch(/^<div/);
	});
});

describe('stripJsxComments', () => {
	it('removes block-comment-only groups', () => {
		expect(stripJsxComments('<div>{/* note */}<b /></div>')).toBe('<div><b /></div>');
	});

	it('removes line-comment-only groups', () => {
		expect(stripJsxComments('<div>{ // note \n }<b /></div>')).toBe('<div><b /></div>');
	});

	it('removes groups with mixed comments', () => {
		expect(stripJsxComments('<div>{ /* a */ // b\n /* c */ }<b /></div>')).toBe('<div><b /></div>');
	});

	it('keeps empty braces', () => {
		expect(stripJsxComments('<div style={{}} />')).toBe('<div style={{}} />');
		expect(stripJsxComments('<div>{}</div>')).toBe('<div>{}</div>');
	});

	it('keeps code groups', () => {
		expect(stripJsxComments('<div>{a}</div>')).toBe('<div>{a}</div>');
		expect(stripJsxComments('<div>{/* c */ a}</div>')).toBe('<div>{/* c */ a}</div>');
	});

	it('keeps unterminated comments', () => {
		expect(stripJsxComments('<div>{/* x')).toBe('<div>{/* x');
		expect(stripJsxComments('<div>{// x')).toBe('<div>{// x');
	});

	it('handles pathological input in linear time', () => {
		const input = '{ /* '.repeat(50_000);
		const start = performance.now();
		const out = stripJsxComments(input);
		expect(performance.now() - start).toBeLessThan(200);
		expect(out).toBe(input);
	});

	it('is linear for repeated block-comment openers with a late close', () => {
		const input = '{/*'.repeat(20_000) + '*/x';
		const start = performance.now();
		const out = stripJsxComments(input);
		expect(performance.now() - start).toBeLessThan(300);
		expect(out).toBe(input);
	});

	it('is linear for repeated line-comment openers', () => {
		const input = '{//'.repeat(20_000);
		const start = performance.now();
		const out = stripJsxComments(input);
		expect(performance.now() - start).toBeLessThan(300);
		expect(out).toBe(input);
	});

	it('treats unicode whitespace like \\s', () => {
		for (const ws of ['\u00a0', '\u2028', '\u2029', '\ufeff']) {
			expect(stripJsxComments(`<div>{${ws}/* c */${ws}}<b /></div>`)).toBe('<div><b /></div>');
		}
	});
});
