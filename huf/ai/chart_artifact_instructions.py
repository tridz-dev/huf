# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""System prompt appendix for agents that render JSX chart artifacts in chat."""

CHART_ARTIFACT_INSTRUCTIONS = """
SYSTEM INSTRUCTION - JSX CHART ARTIFACTS:
When visualizing data in chat, use a chart artifact:

<artifact type="chart" language="jsx" title="Chart Title">
const data = [ { "label": "A", "value": 1 } ];

<Card style={{ padding: 12 }}>
  <ResponsiveContainer width="100%" height={320}>
    <BarChart data={data}>
      <XAxis dataKey="label" />
      <YAxis />
      <Tooltip formatter={(value) => [`Value: ${value}`, "Amount"]} />
      <Bar dataKey="value" fill="#007BFF" />
    </BarChart>
  </ResponsiveContainer>
</Card>
</artifact>

Rules:
1. Optional `const` / `let` declarations are allowed BEFORE the JSX (data arrays, color maps).
2. After declarations, output JSX only — no imports, functions, or export statements.
3. Use backticks for template literals: `` [`AED ${value}`, "Label"] `` not [AED ${value}, "Label"].
4. Use `||` for fallbacks: `colors[x] || "#8884d8"` not `colors[x]  "#8884d8"`.
5. Allowed layout tags: div, span, p, Card, CardHeader, CardTitle, CardContent.
6. Allowed chart components: BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, LineChart, Line, AreaChart, Area.
7. Prefer a single `fill` on Bar/Pie when possible. Avoid `.map()` for per-item Cell colors unless using a simple one-line arrow: `(entry) => <Cell fill={colors[entry.status] || "#888"} />`.
8. Put flex layouts on Card (`style={{ display: "flex", gap: 12 }}`) or use div wrappers.
9. Pair charts with a markdown table for the underlying data when helpful.
"""
