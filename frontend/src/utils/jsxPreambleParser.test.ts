import { describe, expect, it } from 'vitest';
import { extractJsxAndBindings, splitPreambleAndJsx } from './jsxPreambleParser';

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
