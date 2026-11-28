// @vitest-environment jsdom
import { Children, cloneElement, isValidElement, type ReactElement, type ReactNode } from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { JSXPreview } from './jsx-preview';

// jsdom has no layout, so give the chart a fixed size instead of measuring.
const FixedSize = ({ children }: { children?: ReactNode }) => {
	const chart = Children.toArray(children).find(
		(c) => isValidElement(c) && /Chart/.test((c.type as { displayName?: string }).displayName ?? ''),
	);
	return chart ? cloneElement(chart as ReactElement<Record<string, unknown>>, { width: 400, height: 320 }) : null;
};

const DATA = '[{"label": "A", "value": 1}, {"label": "B", "value": 2}, {"label": "C", "value": 3}]';
const COLORS = '["#007BFF", "#28A745", "#FFC107"]';

// Exact output shape of render_chart (pie) in huf/ai/tools/render_tools.py.
const TOOL_PIE = `const data = ${DATA};

const colors = ${COLORS};

<Card style={{ padding: 12 }}>
  <ResponsiveContainer width="100%" height={320}>
    <PieChart>
      <Pie data={data} dataKey="value" nameKey="label" outerRadius={120}>
        {data.map((entry, index) => (
          <Cell key={\`cell-\${index}\`} fill={colors[index % colors.length] || "#8884d8"} />
        ))}
      </Pie>
      <Tooltip />
      <Legend />
    </PieChart>
  </ResponsiveContainer>
</Card>`;

// Documented pattern: fill carried in the data rows, no .map.
const FILL_PIE = `const data = [{"label": "A", "value": 1, "fill": "#007BFF"}, {"label": "B", "value": 2, "fill": "#28A745"}];

<Card style={{ padding: 12 }}>
  <ResponsiveContainer width="100%" height={320}>
    <PieChart>
      <Pie data={data} dataKey="value" nameKey="label" outerRadius={120} />
      <Tooltip />
      <Legend />
    </PieChart>
  </ResponsiveContainer>
</Card>`;

function renderPie(jsx: string) {
	return render(<JSXPreview jsx={jsx} components={{ ResponsiveContainer: FixedSize }} />);
}

describe('JSXPreview pie charts', () => {
	it('draws one slice per row for the render_chart tool output', () => {
		const { container } = renderPie(TOOL_PIE);
		expect(container.textContent).not.toContain('Failed to render JSX');
		expect(container.querySelectorAll('.recharts-pie-sector').length).toBe(3);
	});

	it('draws slices for the per-row fill pattern', () => {
		const { container } = renderPie(FILL_PIE);
		expect(container.textContent).not.toContain('Failed to render JSX');
		expect(container.querySelectorAll('.recharts-pie-sector').length).toBe(2);
	});
});
