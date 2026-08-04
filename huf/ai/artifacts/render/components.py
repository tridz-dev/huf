# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Component registry: the single source of truth for document components.

Both the PDF stylesheet (via ``components_css()``, appended to
``PRINT_STYLESHEET`` in huf/ai/artifacts/render/html.py) and the DOCX
renderer (a later task) are meant to read FROM this dict rather than from
each other. Each component is a CSS class name mapping to exactly two keys:

- "css": the CSS rules that give the component its look in the browser
  preview and in the WeasyPrint PDF render.
- "docx": a RECIPE (a plain dict of instructions, not code) describing how
  the DOCX interpreter should build the equivalent element out of
  python-docx primitives. Keeping this a data recipe - rather than a
  function - is what prevents the two renderers from drifting apart: there
  is nowhere else for either renderer to invent its own idea of what
  "doc-header" means.

Palette (restrained corporate, matches the PDF print context):
	accent #2C5AA8   - brand blue, used for emphasis and header fills
	ink    #16294D   - primary text on light backgrounds
	muted  #6B7891   - secondary/label text
	rule   #D9E0EC   - hairlines and separators
"""

ACCENT = "#2C5AA8"
INK = "#16294D"
MUTED = "#6B7891"
RULE = "#D9E0EC"


#: Single source of truth for document components. Every entry MUST have
#: both a "css" and a "docx" key - see huf/t_h2_verify.py (a) for the
#: anti-drift assertion that enforces this.
COMPONENTS = {
	"doc-header": {
		"css": f"""
.doc-header {{
	display: flex;
	justify-content: space-between;
	align-items: baseline;
	padding-bottom: 8pt;
	margin-bottom: 16pt;
	border-bottom: 1.5pt solid {ACCENT};
}}
""",
		"docx": {"type": "table", "cols": 2, "borders": False, "col_align": ["left", "right"]},
	},
	"brand": {
		"css": f"""
.brand {{
	font-weight: bold;
	letter-spacing: 0.08em;
	text-transform: uppercase;
	color: {ACCENT};
	font-size: 13pt;
}}
""",
		"docx": {"type": "run", "bold": True, "color": "2C5AA8"},
	},
	"doc-meta": {
		"css": f"""
.doc-meta {{
	text-align: right;
	font-size: 8pt;
	color: {MUTED};
}}
""",
		"docx": {"type": "paragraph", "align": "right", "size_pt": 8},
	},
	"doc-title": {
		"css": f"""
.doc-title {{
	font-size: 26pt;
	font-weight: bold;
	color: {INK};
	margin-top: 0.4em;
	margin-bottom: 0.1em;
}}
""",
		"docx": {"type": "heading", "level": 1},
	},
	"doc-subtitle": {
		"css": f"""
.doc-subtitle {{
	font-size: 12pt;
	color: {MUTED};
	margin-top: 0;
	margin-bottom: 1em;
}}
""",
		"docx": {"type": "paragraph", "size_pt": 12, "color": "5C6B85"},
	},
	"callout": {
		"css": f"""
.callout {{
	border-left: 4pt solid {ACCENT};
	background-color: #EAF2FD;
	padding: 10pt 14pt;
	margin: 12pt 0;
}}
""",
		"docx": {"type": "table", "cols": 1, "shading": "EAF2FD", "borders": True},
	},
	"metric-grid": {
		# CSS Grid, deliberately NOT flex-wrap. WeasyPrint's flex layout does
		# not wrap: measured against A4, `display:flex;flex-wrap:wrap` with
		# `flex:0 0 48%`, `flex:0 0 calc(50% - 5pt)` and `width:48%` ALL
		# stacked the four cards into 4 rows x 1 column. Grid produces a true
		# 2x2 (cards at x=83.6/403.5 across two rows). Non-wrapping flex is
		# fine and is still used by .split.
		"css": """
.metric-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 10pt;
	margin: 12pt 0;
}
""",
		"docx": {"type": "table_row_of_cells", "source": "children"},
	},
	"metric": {
		# Cards form a 2x2 grid on A4: each card takes ~calc(50% - gap/2) of
		# the .metric-grid row, wrapping after two. The label is written
		# ONCE by the author as a data-label attribute and rendered via a
		# ::after pseudo-element's content: attr(data-label) - verified to
		# render correctly under WeasyPrint (huf/t_h2_verify.py, check e).
		"css": f"""
.metric {{
	flex: 0 0 calc(50% - 5pt);
	background-color: #F7FAFD;
	border: 0.75pt solid {RULE};
	border-radius: 3pt;
	padding: 10pt 12pt;
	font-size: 16pt;
	font-weight: bold;
	color: {INK};
}}

.metric::after {{
	content: attr(data-label);
	display: block;
	margin-top: 4pt;
	font-size: 7pt;
	font-weight: normal;
	letter-spacing: 0.06em;
	text-transform: uppercase;
	color: {MUTED};
}}
""",
		"docx": {
			"type": "cell",
			"shading": "F7FAFD",
			"value_size_pt": 16,
			"label_size_pt": 7,
			"label_from": "data-label",
		},
	},
	"split": {
		"css": """
.split {
	display: flex;
	gap: 16pt;
	margin: 12pt 0;
}
""",
		"docx": {"type": "table", "cols": 2, "borders": False, "widths": [0.66, 0.34]},
	},
	"split-main": {
		"css": """
.split-main {
	flex: 0 0 66%;
}
""",
		"docx": {"type": "cell"},
	},
	"split-side": {
		"css": f"""
.split-side {{
	flex: 0 0 calc(34% - 16pt);
	background-color: #F6F9FC;
	border: 0.75pt solid {RULE};
	border-radius: 3pt;
	padding: 10pt 12pt;
}}
""",
		"docx": {"type": "cell", "shading": "F6F9FC"},
	},
	"data-table": {
		"css": f"""
.data-table {{
	width: 100%;
	border-collapse: collapse;
	margin: 12pt 0;
}}

.data-table th {{
	background-color: {ACCENT};
	color: #FFFFFF;
	font-weight: bold;
	text-align: left;
	padding: 6pt 8pt;
	border: none;
}}

.data-table td {{
	padding: 6pt 8pt;
	border: none;
	border-bottom: 0.75pt solid {RULE};
}}
""",
		"docx": {"type": "table", "style": "Table Grid", "header_shading": "2C5AA8", "header_color": "FFFFFF"},
	},
	"doc-footer": {
		"css": f"""
.doc-footer {{
	font-size: 7.5pt;
	color: {MUTED};
	margin-top: 20pt;
	padding-top: 6pt;
	border-top: 0.75pt solid {RULE};
}}
""",
		"docx": {"type": "paragraph", "size_pt": 7.5, "color": "8A93A5"},
	},
}


#: The registry's keys, exposed for fast membership lookup by the DOCX
#: renderer (e.g. "is this element's class a known component?").
COMPONENT_CLASSES = frozenset(COMPONENTS.keys())


def components_css() -> str:
	"""Concatenate every component's "css" entry into one stylesheet chunk.

	Appended after PRINT_STYLESHEET's existing rules in html.py, so this is
	the only place component CSS is authored - the PDF and browser preview
	both consume it, and the DOCX "docx" recipes live right next to it in
	COMPONENTS so the two can never describe different components.
	"""
	return "\n".join(COMPONENTS[class_name]["css"] for class_name in COMPONENT_CLASSES)
