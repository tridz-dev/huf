# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Component registry: the single source of truth for document components.

Both the PDF stylesheet (via ``components_css()``, appended to
``PRINT_STYLESHEET`` in huf/ai/artifacts/render/html.py) and the DOCX
renderer read FROM this dict rather than from each other. Each component is
a CSS class name mapping to exactly two keys:

- "css": the CSS rules that give the component its look in the browser
  preview and in the WeasyPrint PDF render.
- "docx": a RECIPE (a plain dict of instructions, not code) describing how
  the DOCX interpreter should build the equivalent element out of
  python-docx primitives. Keeping this a data recipe - rather than a
  function - is what prevents the two renderers from drifting apart: there
  is nowhere else for either renderer to invent its own idea of what
  "doc-header" means.

Theming
-------
Colours are NOT written literally into either side. They are declared once
in ``THEME`` and referenced as CSS custom properties (``var(--accent)``) in
the "css" entries and as the same ``var(--token)`` strings in the "docx"
recipes. That indirection is what makes the two renderers agree on a
RE-THEMED document, not just on the default palette.

The failure this fixes was observed in production: an agent authored a
document whose own <style> block redefined .doc-header/.callout/.metric to a
red-and-black palette. WeasyPrint honoured it (the <style> block sits in the
body, after the head stylesheet, so it wins the cascade) while the DOCX
renderer - which only ever consulted this registry's hardcoded hex values -
emitted the default blue. Same document, two different colour schemes.

With theme variables the agent re-themes by setting the custom properties
once in a ``:root`` rule, and the DOCX renderer parses that ONE rule to
recolour every recipe (see huf/ai/artifacts/render/docx.py). Overriding a
whole component class by hand still only reaches the PDF, which is why the
authoring prompt steers to the variables instead.

WeasyPrint 68 resolves ``var()`` correctly - verified by rendering
``--accent: #D32F2F`` and reading back ``srgb 0.827 0.184 0.184``.
"""

#: Default palette (restrained corporate, matches the PDF print context).
#: Keys are CSS custom-property names WITHOUT the leading "--".
#:
#: Every value must be a plain ``#RRGGBB`` literal: the DOCX renderer feeds
#: these straight to OOXML, which has no notion of colour functions.
THEME = {
	"accent": "#2C5AA8",  # brand colour: header rules, table header fill, emphasis
	"accent-contrast": "#FFFFFF",  # text drawn on top of --accent
	"ink": "#16294D",  # primary text on light backgrounds
	"muted": "#6B7891",  # secondary / label text
	"rule": "#D9E0EC",  # hairlines and separators
	"surface": "#F7FAFD",  # card and sidebar fills
	"callout-bg": "#EAF2FD",  # callout box fill
}

#: Back-compat aliases. Other modules imported these names before theming
#: existed; keeping them avoids a pointless churn of unrelated call sites.
ACCENT = THEME["accent"]
INK = THEME["ink"]
MUTED = THEME["muted"]
RULE = THEME["rule"]


def theme_css() -> str:
	"""The default theme as a ``:root`` custom-property block.

	Emitted FIRST in the generated stylesheet so an author's own ``:root``
	rule (which lands later in the cascade, in the body) overrides it
	wholesale. Nothing else needs to know the defaults.
	"""
	declarations = "\n".join(f"\t--{token}: {value};" for token, value in THEME.items())
	return f":root {{\n{declarations}\n}}\n"


def resolve_theme_token(value: str, theme: dict | None = None) -> str:
	"""Resolve a ``var(--token)`` recipe value to a ``#RRGGBB`` literal.

	Recipe colours are stored as ``var(--accent)`` rather than as hex so a
	re-themed document produces a re-themed DOCX. ``theme`` is the document's
	effective palette (defaults merged with whatever the author set in
	``:root``); anything that is not a ``var(...)`` reference is returned
	untouched, so a recipe may still carry a literal when a fixed colour is
	genuinely intended.
	"""
	if not isinstance(value, str) or not value.startswith("var("):
		return value

	token = value[len("var(") : -1].strip().lstrip("-")
	palette = theme or THEME

	return palette.get(token) or THEME.get(token) or value


#: Single source of truth for document components. Every entry MUST have
#: both a "css" and a "docx" key, and every colour in either half MUST be a
#: var(--token) reference rather than a literal - a hardcoded hex is exactly
#: how a re-themed document produced a red PDF and a blue Word file. Both
#: invariants are asserted in huf/ai/tests/test_document_render.py.
COMPONENTS = {
	"doc-header": {
		"css": """
.doc-header {
	display: flex;
	justify-content: space-between;
	align-items: baseline;
	padding-bottom: 8pt;
	margin-bottom: 16pt;
	border-bottom: 1.5pt solid var(--accent);
}
""",
		"docx": {"type": "table", "cols": 2, "borders": False, "col_align": ["left", "right"]},
	},
	"brand": {
		"css": """
.brand {
	font-weight: bold;
	letter-spacing: 0.08em;
	text-transform: uppercase;
	color: var(--accent);
	font-size: 13pt;
}
""",
		"docx": {"type": "run", "bold": True, "color": "var(--accent)"},
	},
	"doc-meta": {
		"css": """
.doc-meta {
	text-align: right;
	font-size: 8pt;
	color: var(--muted);
}
""",
		"docx": {"type": "paragraph", "align": "right", "size_pt": 8},
	},
	"doc-title": {
		"css": """
.doc-title {
	font-size: 26pt;
	font-weight: bold;
	color: var(--ink);
	margin-top: 0.4em;
	margin-bottom: 0.1em;
}
""",
		"docx": {"type": "heading", "level": 1},
	},
	"doc-subtitle": {
		"css": """
.doc-subtitle {
	font-size: 12pt;
	color: var(--muted);
	margin-top: 0;
	margin-bottom: 1em;
}
""",
		"docx": {"type": "paragraph", "size_pt": 12, "color": "var(--muted)"},
	},
	"callout": {
		"css": """
.callout {
	border-left: 4pt solid var(--accent);
	background-color: var(--callout-bg);
	padding: 10pt 14pt;
	margin: 12pt 0;
}
""",
		"docx": {"type": "table", "cols": 1, "shading": "var(--callout-bg)", "borders": True},
	},
	"metric-grid": {
		# CSS Grid, deliberately NOT flex-wrap. WeasyPrint's flex layout does
		# not wrap: measured against A4, `display:flex;flex-wrap:wrap` with
		# `flex:0 0 48%`, `flex:0 0 calc(50% - 5pt)` and `width:48%` ALL
		# stacked the four cards into 4 rows x 1 column. Grid produces a true
		# 2x2 (cards at x=83.6/403.5 across two rows).
		#
		# Grid also fragments correctly across page boundaries, which flex
		# does not - see the .split comment below.
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
		# The label is written ONCE by the author as a data-label attribute
		# and rendered via a ::after pseudo-element's content: attr(data-label)
		# - verified to render correctly under WeasyPrint.
		"css": """
.metric {
	background-color: var(--surface);
	border: 0.75pt solid var(--rule);
	border-radius: 3pt;
	padding: 10pt 12pt;
	font-size: 16pt;
	font-weight: bold;
	color: var(--ink);
}

.metric::after {
	content: attr(data-label);
	display: block;
	margin-top: 4pt;
	font-size: 7pt;
	font-weight: normal;
	letter-spacing: 0.06em;
	text-transform: uppercase;
	color: var(--muted);
}
""",
		"docx": {
			"type": "cell",
			"shading": "var(--surface)",
			"value_size_pt": 16,
			"value_color": "var(--ink)",
			"label_size_pt": 7,
			"label_color": "var(--muted)",
			"label_from": "data-label",
		},
	},
	"split": {
		# GRID, not flex, and this is load-bearing rather than stylistic.
		#
		# WeasyPrint 68 will not START a flex container part-way down a page
		# when its content is tall enough to need fragmenting - it pushes the
		# whole box to the top of the next page and only fragments from
		# there. Measured: with the full 25.7cm content area free, a tall
		# flex .split still began on page 2, while an identical plain block
		# filled the remaining space correctly. In a real document that
		# showed up as ~40% of a page left blank ahead of every sidebar
		# section.
		#
		# Flex has a second defect here: given a tall main column and a short
		# sidebar, it lays out every main-column fragment first and paints the
		# sidebar only in the LAST fragment - stranding the sidebar pages away
		# from the content it annotates.
		#
		# Grid has neither problem: it starts in the space available and
		# fragments cell content cleanly across the break.
		"css": """
.split {
	display: grid;
	grid-template-columns: 2fr 1fr;
	gap: 16pt;
	margin: 12pt 0;
}
""",
		"docx": {"type": "table", "cols": 2, "borders": False, "widths": [0.66, 0.34]},
	},
	"split-main": {
		"css": """
.split-main {
	min-width: 0;
}
""",
		"docx": {"type": "cell"},
	},
	"split-side": {
		"css": """
.split-side {
	min-width: 0;
	align-self: start;
	background-color: var(--surface);
	border: 0.75pt solid var(--rule);
	border-radius: 3pt;
	padding: 10pt 12pt;
}
""",
		"docx": {"type": "cell", "shading": "var(--surface)"},
	},
	"data-table": {
		"css": """
.data-table {
	width: 100%;
	border-collapse: collapse;
	margin: 12pt 0;
}

.data-table th {
	background-color: var(--accent);
	color: var(--accent-contrast);
	font-weight: bold;
	text-align: left;
	padding: 6pt 8pt;
	border: none;
}

.data-table td {
	padding: 6pt 8pt;
	border: none;
	border-bottom: 0.75pt solid var(--rule);
}
""",
		"docx": {
			"type": "table",
			"style": "Table Grid",
			"header_shading": "var(--accent)",
			"header_color": "var(--accent-contrast)",
		},
	},
	"status-badge": {
		# Added because agents kept inventing it: an inline pill next to a
		# table row's status. Without a registry entry the text survived into
		# the DOCX but lost all styling, since docx.py only styles known
		# component classes.
		"css": """
.status-badge {
	display: inline-block;
	padding: 1pt 5pt;
	border-radius: 2pt;
	background-color: var(--rule);
	color: var(--ink);
	font-size: 7.5pt;
	font-weight: bold;
	letter-spacing: 0.04em;
	text-transform: uppercase;
}
""",
		"docx": {"type": "run", "bold": True, "size_pt": 7.5, "shading": "var(--rule)", "color": "var(--ink)"},
	},
	"page-break": {
		# Deliberately invisible. An agent-authored version of this carried
		# `height: 1px; border-bottom: 1px dashed` and WeasyPrint PAINTED it -
		# a stray dashed rule appeared in the exported PDF just above every
		# forced break. Forcing a break and drawing a divider are different
		# jobs; this one only breaks.
		"css": """
.page-break {
	break-after: page;
	display: block;
	height: 0;
	border: none;
	margin: 0;
}
""",
		"docx": {"type": "page_break"},
	},
	"doc-footer": {
		# A running footer, not body content. Authors previously hand-wrote
		# "CONFIDENTIAL - PAGE 1 OF 2" as an ordinary paragraph, which
		# appeared exactly once, mid-flow, with a hard-coded page count that
		# was wrong the moment pagination changed.
		#
		# position: running(foot) lifts the element out of normal flow, and
		# html.py's @page rule pulls it into the bottom-left margin box on
		# EVERY page via content: element(foot). Page numbering is a separate
		# margin box using counter(page)/counter(pages), so the author never
		# writes a page number at all.
		#
		# Verified working under WeasyPrint 68.
		"css": """
.doc-footer {
	position: running(foot);
	font-size: 7.5pt;
	color: var(--muted);
}
""",
		"docx": {"type": "footer", "size_pt": 7.5, "color": "var(--muted)"},
	},
}


#: The registry's keys, exposed for fast membership lookup by the DOCX
#: renderer (e.g. "is this element's class a known component?").
COMPONENT_CLASSES = frozenset(COMPONENTS.keys())


def components_css() -> str:
	"""The theme block followed by every component's "css" entry.

	Appended after PRINT_STYLESHEET's existing rules in html.py, so this is
	the only place component CSS is authored - the PDF and browser preview
	both consume it, and the DOCX "docx" recipes live right next to it in
	COMPONENTS so the two can never describe different components.

	Iterates COMPONENTS (insertion-ordered) rather than COMPONENT_CLASSES (a
	frozenset) so the emitted stylesheet is byte-stable between runs; with a
	set the rule order shifted per process, which made cascade behaviour
	between same-specificity rules non-deterministic.
	"""
	rules = "\n".join(component["css"] for component in COMPONENTS.values())
	return theme_css() + rules
