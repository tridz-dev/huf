# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Agent-facing tool handlers that template structured JSON into the existing
Mermaid/chart <artifact> tag formats, so a model passes data instead of
hand-authoring Mermaid DSL or Recharts JSX.

Both handlers return the complete <artifact>...</artifact> markup string -
the exact same tags a model would otherwise hand-author - or raise ValueError
on bad input, matching the convention used elsewhere in huf/ai/tools/.
"""

import json

VALID_DIAGRAM_TYPES = ("graph TD", "graph LR", "flowchart TD", "flowchart LR")
VALID_CHART_TYPES = ("bar", "line", "pie", "area")

# Characters that break Mermaid node/edge syntax inside a label.
_MERMAID_LABEL_ESCAPES = {
	"[": "(",
	"]": ")",
	"|": "-",
	'"': "'",
}

# Default palette for pie-chart slices when the caller does not supply colors.
_DEFAULT_PIE_COLORS = ["#007BFF", "#28A745", "#FFC107", "#DC3545", "#6F42C1", "#20C997", "#FD7E14"]


def _escape_mermaid_label(label: str) -> str:
	escaped = label
	for char, replacement in _MERMAID_LABEL_ESCAPES.items():
		escaped = escaped.replace(char, replacement)
	return escaped


def _escape_artifact_attr(value: str) -> str:
	"""Sanitize a value that will be templated into an `<artifact ...>` tag
	attribute (e.g. title="...").

	The frontend's artifact parser (frontend/src/utils/artifactParser.ts)
	extracts the outer `<artifact ...>` tag with a plain regex, not an HTML/DOM
	parser: `ARTIFACT_REGEX` stops at the first `>` and `ATTR_REGEX` stops at
	the first matching quote. An unescaped `"` or `>` in a templated value
	(e.g. an LLM- or user-supplied chart/diagram title) would truncate or
	corrupt the tag boundary, leaking the rest of the artifact body as raw
	text into the chat. Strip the characters that matter to that regex rather
	than trying to HTML-encode them (this isn't HTML, so entities like
	`&quot;` would just render literally).
	"""
	if not value:
		return value
	return value.replace('"', "'").replace("<", "(").replace(">", ")")


def _escape_jsx_attr(value: str) -> str:
	"""Sanitize a value templated into a double-quoted JSX attribute
	(e.g. dataKey="...", fill="..."). Prevents a caller-supplied field name or
	color from closing the attribute early and injecting additional JSX
	attributes/props into the generated chart component.
	"""
	if not value:
		return value
	return value.replace('"', "'").replace("{", "(").replace("}", ")")


def handle_render_mermaid(diagram_type=None, nodes=None, edges=None, title=None, **kwargs) -> str:
	"""Template structured nodes/edges into a Mermaid <artifact> tag.

	Args:
		diagram_type (str): One of "graph TD", "graph LR", "flowchart TD", "flowchart LR".
		nodes (list[dict]): Each {"id": str, "label": str, "shape": optional, ignored}.
		edges (list[dict]): Each {"from": str, "to": str, "label": optional str}.
		title (str): Artifact title, defaults to "Diagram".

	Returns:
		The complete <artifact type="mermaid" ...>...</artifact> string.
	"""
	if diagram_type not in VALID_DIAGRAM_TYPES:
		raise ValueError(f"'diagram_type' must be one of {VALID_DIAGRAM_TYPES}, got {diagram_type!r}")

	if not isinstance(nodes, list) or not nodes:
		raise ValueError("'nodes' must be a non-empty list of {id, label} objects")

	if edges is None:
		edges = []
	if not isinstance(edges, list):
		raise ValueError("'edges' must be a list of {from, to, label} objects")

	node_ids = set()
	node_lines = []
	for i, node in enumerate(nodes):
		if not isinstance(node, dict):
			raise ValueError(f"nodes[{i}] must be an object with 'id' and 'label'")
		node_id = (node.get("id") or "").strip()
		label = (node.get("label") or "").strip()
		if not node_id:
			raise ValueError(f"nodes[{i}] is missing a required non-empty 'id'")
		if not label:
			raise ValueError(f"nodes[{i}] (id={node_id!r}) is missing a required non-empty 'label'")
		if node_id in node_ids:
			raise ValueError(f"Duplicate node id {node_id!r} - node ids must be unique")
		node_ids.add(node_id)
		node_lines.append(f"    {node_id}[{_escape_mermaid_label(label)}]")

	edge_lines = []
	for i, edge in enumerate(edges):
		if not isinstance(edge, dict):
			raise ValueError(f"edges[{i}] must be an object with 'from' and 'to'")
		src = (edge.get("from") or "").strip()
		dst = (edge.get("to") or "").strip()
		if not src or not dst:
			raise ValueError(f"edges[{i}] must have non-empty 'from' and 'to'")
		if src not in node_ids:
			raise ValueError(f"edges[{i}] references unknown node id 'from'={src!r} - it must match a declared node id")
		if dst not in node_ids:
			raise ValueError(f"edges[{i}] references unknown node id 'to'={dst!r} - it must match a declared node id")

		edge_label = (edge.get("label") or "").strip()
		if edge_label:
			edge_lines.append(f"    {src} -->|{_escape_mermaid_label(edge_label)}| {dst}")
		else:
			edge_lines.append(f"    {src} --> {dst}")

	dsl_lines = [diagram_type] + node_lines + edge_lines
	dsl = "\n".join(dsl_lines)

	_sanity_check_mermaid_dsl(dsl)

	artifact_title = _escape_artifact_attr((title or "Diagram").strip())
	return f'<artifact type="mermaid" title="{artifact_title}">\n{dsl}\n</artifact>'


def _sanity_check_mermaid_dsl(dsl: str) -> None:
	"""Best-effort structural check on generated DSL before returning it."""
	if dsl.count("[") != dsl.count("]"):
		raise ValueError("Generated Mermaid DSL has unbalanced [] brackets - this is a bug in render_mermaid")
	if "[]" in dsl.replace(" ", ""):
		raise ValueError("Generated Mermaid DSL has an empty node label - this is a bug in render_mermaid")
	for line in dsl.splitlines()[1:]:
		stripped = line.strip()
		if not stripped:
			continue
		is_edge_line = "-->" in stripped
		is_node_line = "[" in stripped
		if stripped.startswith("-->") or not (is_edge_line or is_node_line):
			raise ValueError(f"Generated Mermaid DSL line looks malformed: {stripped!r}")


_CHART_TAG_TEMPLATES = {
	"bar": {
		"import_component": "BarChart",
		"series_component": "Bar",
	},
	"line": {
		"import_component": "LineChart",
		"series_component": "Line",
	},
	"area": {
		"import_component": "AreaChart",
		"series_component": "Area",
	},
}


def handle_render_chart(chart_type=None, data=None, series_keys=None, x_key="label", colors=None, title=None, **kwargs) -> str:
	"""Template structured data into a JSX chart <artifact> tag matching the
	rules in huf.ai.chart_artifact_instructions (allowed tags/components,
	backtick template literals, no CardHeader/CardTitle, etc).

	Args:
		chart_type (str): One of "bar", "line", "pie", "area".
		data (list[dict]): Non-empty rows, each containing at least x_key.
		series_keys (list[str]): Fields to plot; defaults to ["value"].
		x_key (str): Field used for the category/x axis. Ignored for "pie".
		colors (list[str]): Optional palette, mainly used for pie slices.
		title (str): Artifact title.

	Returns:
		The complete <artifact type="chart" language="jsx" ...>...</artifact> string.
	"""
	if chart_type not in VALID_CHART_TYPES:
		raise ValueError(f"'chart_type' must be one of {VALID_CHART_TYPES}, got {chart_type!r}")

	if not isinstance(data, list) or not data:
		raise ValueError("'data' must be a non-empty list of objects")

	for i, row in enumerate(data):
		if not isinstance(row, dict):
			raise ValueError(f"data[{i}] must be an object")
		if chart_type != "pie" and x_key not in row:
			raise ValueError(f"data[{i}] is missing the required x_key field {x_key!r}")

	if not series_keys:
		series_keys = ["value"]
	if not isinstance(series_keys, list) or not series_keys:
		raise ValueError("'series_keys' must be a non-empty list of field names")

	for i, row in enumerate(data):
		for key in series_keys:
			if key not in row:
				raise ValueError(f"data[{i}] is missing series_key field {key!r}")

	data_declaration = f"const data = {json.dumps(data)};"
	artifact_title = _escape_artifact_attr((title or f"{chart_type.capitalize()} Chart").strip())

	if chart_type == "pie":
		jsx = _build_pie_jsx(series_keys[0], colors)
	else:
		jsx = _build_axis_chart_jsx(chart_type, x_key, series_keys, colors)

	body = f"{data_declaration}\n\n{jsx}"
	return f'<artifact type="chart" language="jsx" title="{artifact_title}">\n{body}\n</artifact>'


def _build_axis_chart_jsx(chart_type: str, x_key: str, series_keys: list, colors) -> str:
	template = _CHART_TAG_TEMPLATES[chart_type]
	container = template["import_component"]
	series_component = template["series_component"]
	palette = colors or _DEFAULT_PIE_COLORS

	series_lines = []
	for i, key in enumerate(series_keys):
		color = _escape_jsx_attr(str(palette[i % len(palette)]))
		safe_key = _escape_jsx_attr(str(key))
		series_lines.append(f'      <{series_component} dataKey="{safe_key}" fill="{color}" stroke="{color}" />')
	series_jsx = "\n".join(series_lines)

	safe_x_key = _escape_jsx_attr(str(x_key))
	return (
		"<Card style={{ padding: 12 }}>\n"
		'  <ResponsiveContainer width="100%" height={320}>\n'
		f"    <{container} data={{data}}>\n"
		f'      <XAxis dataKey="{safe_x_key}" />\n'
		"      <YAxis />\n"
		"      <Tooltip />\n"
		"      <Legend />\n"
		f"{series_jsx}\n"
		f"    </{container}>\n"
		"  </ResponsiveContainer>\n"
		"</Card>"
	)


def _build_pie_jsx(value_key: str, colors) -> str:
	palette = colors or _DEFAULT_PIE_COLORS
	colors_declaration = f"const colors = {json.dumps(palette)};"
	safe_value_key = _escape_jsx_attr(str(value_key))

	return (
		f"{colors_declaration}\n\n"
		"<Card style={{ padding: 12 }}>\n"
		'  <ResponsiveContainer width="100%" height={320}>\n'
		"    <PieChart>\n"
		f'      <Pie data={{data}} dataKey="{safe_value_key}" nameKey="label" outerRadius={{120}}>\n'
		"        {data.map((entry, index) => (\n"
		'          <Cell key={`cell-${index}`} fill={colors[index % colors.length] || "#8884d8"} />\n'
		"        ))}\n"
		"      </Pie>\n"
		"      <Tooltip />\n"
		"      <Legend />\n"
		"    </PieChart>\n"
		"  </ResponsiveContainer>\n"
		"</Card>"
	)
