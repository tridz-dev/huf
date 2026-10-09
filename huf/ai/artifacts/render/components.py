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

from huf.ai.artifacts.render import design_tokens as tokens


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


#: Used when a var(--x) reference cannot be resolved at all.
SAFE_DEFAULT_COLOR = "#000000"


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

	inner = value[len("var(") :].rstrip()
	if inner.endswith(")"):
		inner = inner[:-1]
	name, _, fallback = inner.partition(",")
	token = name.strip().lstrip("-")
	fallback = fallback.strip()
	palette = theme or THEME

	resolved = palette.get(token) or THEME.get(token)
	if resolved:
		return resolved
	if fallback:
		# A fallback may itself be a var(...) reference.
		if fallback.startswith("var("):
			return resolve_theme_token(fallback, theme)
		return fallback
	return SAFE_DEFAULT_COLOR


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
	gap: 12pt;
	padding-bottom: 6pt;
	margin-bottom: 18pt;
	border-bottom: 1pt solid var(--accent);
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
	font-size: __CAPTION_PT__pt;
	line-height: 1.3;
}
""",
		"docx": {"type": "run", "bold": True, "color": "var(--accent)"},
	},
	"doc-meta": {
		"css": """
.doc-meta {
	text-align: end;
	font-size: __CAPTION_PT__pt;
	line-height: 1.4;
	color: var(--muted);
	white-space: nowrap;
}
""",
		"docx": {"type": "paragraph", "align": "right", "size_pt": tokens.CAPTION_SIZE_PT},
	},
	"doc-title": {
		"css": """
.doc-title {
	font-size: __TITLE_PT__pt;
	font-weight: bold;
	line-height: 1.2;
	letter-spacing: -0.01em;
	color: var(--ink);
	margin-top: 0;
	margin-bottom: 4pt;
}
""",
		# Word's built-in Heading styles carry their OWN colour (a blue that
		# belongs to the default template, not to this document). A themed
		# document therefore came out with a correctly-coloured brand and
		# stubbornly blue headings, which read as "the theme did not apply".
		# The colour is set explicitly on the run instead - matching the PDF,
		# where headings simply inherit the body colour.
		"docx": {"type": "heading", "level": 1, "color": "var(--ink)"},
	},
	"doc-subtitle": {
		"css": """
.doc-subtitle {
	font-size: __SUBTITLE_PT__pt;
	line-height: 1.4;
	color: var(--muted);
	margin-top: 0;
	margin-bottom: 16pt;
}
""",
		"docx": {"type": "paragraph", "size_pt": tokens.SUBTITLE_SIZE_PT, "color": "var(--muted)"},
	},
	"callout": {
		"css": """
.callout {
	border-inline-start: 3pt solid var(--accent);
	border-radius: 0 3pt 3pt 0;
	background-color: var(--callout-bg);
	padding: 8pt 12pt;
	margin: 0 0 12pt;
	break-inside: avoid;
}

.callout > :last-child {
	margin-bottom: 0;
}

.callout h2, .callout h3, .callout h4 {
	margin-top: 0;
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
	grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
	gap: 8pt;
	margin: 0 0 14pt;
}

/* Opt-in denser rows for 3 or 4 short KPIs: class="metric-grid cols-4". */
.metric-grid.cols-3 {
	grid-template-columns: repeat(3, minmax(0, 1fr));
}

.metric-grid.cols-4 {
	grid-template-columns: repeat(4, minmax(0, 1fr));
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
	padding: 8pt 10pt;
	font-size: __METRIC_PT__pt;
	line-height: 1.2;
	font-weight: bold;
	font-variant-numeric: tabular-nums;
	color: var(--ink);
	break-inside: avoid;
}

.metric::after {
	content: attr(data-label);
	display: block;
	margin-top: 4pt;
	font-size: __LABEL_PT__pt;
	font-weight: normal;
	letter-spacing: 0.06em;
	text-transform: uppercase;
	color: var(--muted);
}
""",
		"docx": {
			"type": "cell",
			"shading": "var(--surface)",
			"value_size_pt": tokens.METRIC_VALUE_SIZE_PT,
			"value_color": "var(--ink)",
			"label_size_pt": tokens.LABEL_SIZE_PT,
			"label_color": "var(--muted)",
			"label_from": "data-label",
		},
	},
	"split": {
		# Sidebar robustness. A model-written sidebar must never look broken:
		# the old fixed `1fr 28%` grid gave the aside ~180px at A4 width, so
		# bullets wrapped every one or two words under a big heading.
		#
		# Screen (the in-app preview): flex-wrap with a 420px basis for the
		# main column and a 240px floor for the aside. When both cannot fit
		# side by side the aside wraps BELOW the main column at full width.
		# An A4 preview column is ~643px, so in practice it stacks there and
		# only sits beside the text in a genuinely wide view. A long aside
		# (5+ list items, several paragraphs, a table) always stacks.
		#
		# Print (WeasyPrint): always stacked as plain blocks. A4's content box
		# cannot fit 240 + 420px anyway, and WeasyPrint 68 has two flex defects
		# here - it will not START a tall flex container part-way down a page
		# (leaving ~40% of a page blank), and it paints a short sidebar only in
		# the LAST fragment of a tall main column. Plain blocks have neither.
		#
		# Structural properties are !important: an author <style> block sits
		# after this stylesheet and would otherwise win the cascade (that is
		# how a model-written `grid-template-columns: 1fr 210px` got through).
		"css": """
.split {
	display: flex !important;
	flex-wrap: wrap !important;
	align-items: flex-start;
	gap: 12pt 16pt;
	margin: 0 0 12pt;
}

@media print {
	.split {
		display: block !important;
	}

	.split > .split-side {
		margin-top: 10pt;
	}
}
""",
		# LINEARISED in Word, deliberately, rather than mapped to a two-column
		# table. A nested data-table inside a split cell overflowed the cell it
		# sat in - python-docx leaves autofit on, so the inner table computed a
		# width wider than its container and Word clipped the last column
		# mid-word while the sidebar painted over the top of it.
		#
		# Fixing the widths would have produced a cramped two-column imitation
		# of a web layout. A Word document that flows in a single column reads
		# as deliberate; one that half-imitates a grid reads as broken. So the
		# sidebar drops BELOW the main content instead, and the PDF remains the
		# format that carries the designed layout.
		"docx": {"type": "passthrough"},
	},
	"split-main": {
		"css": """
.split-main {
	flex: 999 1 __MAIN_MIN_PX__px !important;
	min-width: 0 !important;
	max-width: 100%;
}
""",
		"docx": {"type": "passthrough"},
	},
	"split-side": {
		"css": """
.split-side {
	flex: 1 1 __SIDE_MIN_PX__px !important;
	min-width: __SIDE_MIN_PX__px !important;
	max-width: 100%;
	box-sizing: border-box;
	font-family: inherit !important;
	background-color: var(--surface);
	border: 0.75pt solid var(--rule);
	border-radius: 3pt;
	padding: 8pt 10pt;
	font-size: __SIDE_PT__pt !important;
	line-height: 1.45;
	color: var(--ink);
	overflow-wrap: break-word;
	word-break: normal;
	hyphens: manual;
}

/* A long aside is content, not a margin note: give it the full width. */
.split:has(> .split-side li:nth-of-type(5)) > *,
.split:has(> .split-side > p ~ p ~ p) > *,
.split:has(> .split-side table) > * {
	flex-basis: 100% !important;
}

/* The sidebar is a margin note, not a second article: its headings are
   small labels, never section-sized and never a display face. */
.split-side h1, .split-side h2, .split-side h3, .split-side h4,
.split-side h5, .split-side h6 {
	font-family: inherit !important;
	font-size: __LABEL_PT__pt !important;
	font-weight: bold;
	line-height: 1.3 !important;
	letter-spacing: 0.06em;
	text-transform: uppercase;
	color: var(--muted);
	margin: 8pt 0 3pt !important;
}

.split-side p, .split-side li, .split-side td {
	font-size: inherit !important;
}

.split-side > :first-child {
	margin-top: 0;
}

.split-side > :last-child {
	margin-bottom: 0;
}

.split-side p, .split-side ul, .split-side ol {
	margin-bottom: 5pt;
}

.split-side ul, .split-side ol {
	padding-inline-start: __SIDE_INDENT_PT__pt !important;
	margin-inline-start: 0 !important;
}
""",
		# Full-width shaded block once the split is linearised, so the sidebar
		# still reads as an aside rather than as more body copy.
		"docx": {"type": "table", "cols": 1, "shading": "var(--surface)", "borders": True},
	},
	"data-table": {
		"css": """
.data-table {
	width: 100%;
	border-collapse: collapse;
	margin: 12pt 0;
}

.data-table th {
	background-color: var(--surface);
	color: var(--muted);
	font-weight: bold;
	text-align: start;
	padding: 5pt 8pt;
	border: none;
	border-bottom: 1pt solid var(--ink);
}

.data-table td {
	padding: 5pt 8pt;
	border: none;
	border-bottom: 0.75pt solid var(--rule);
}
""",
		"docx": {
			"type": "table",
			"style": "Table Grid",
			"header_shading": "var(--surface)",
			"header_color": "var(--muted)",
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
	padding: 0.5pt 5pt;
	border-radius: 8pt;
	background-color: var(--rule);
	color: var(--ink);
	font-size: __LABEL_PT__pt;
	line-height: 1.5;
	font-weight: bold;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	white-space: nowrap;
	vertical-align: 0.5pt;
}
""",
		"docx": {"type": "run", "bold": True, "size_pt": tokens.LABEL_SIZE_PT, "shading": "var(--rule)", "color": "var(--ink)"},
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
	font-size: __CAPTION_PT__pt;
	color: var(--muted);
}
""",
		"docx": {"type": "footer", "size_pt": tokens.CAPTION_SIZE_PT, "color": "var(--muted)"},
	},
}


#: Component CSS names its sizes by placeholder so every value comes from
#: design_tokens - the same numbers the DOCX recipes above read directly.
_SIZE_PLACEHOLDERS = {
	"__TITLE_PT__": tokens.TITLE_SIZE_PT,
	"__SUBTITLE_PT__": tokens.SUBTITLE_SIZE_PT,
	"__METRIC_PT__": tokens.METRIC_VALUE_SIZE_PT,
	"__CAPTION_PT__": tokens.CAPTION_SIZE_PT,
	"__LABEL_PT__": tokens.LABEL_SIZE_PT,
	"__SIDE_PT__": tokens.SIDE_SIZE_PT,
	"__SIDE_INDENT_PT__": tokens.SIDE_LIST_INDENT_PT,
	"__SIDE_MIN_PX__": tokens.SIDE_MIN_WIDTH_PX,
	"__MAIN_MIN_PX__": tokens.MAIN_MIN_WIDTH_PX,
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
	for placeholder, value in _SIZE_PLACEHOLDERS.items():
		rules = rules.replace(placeholder, str(value))
	return theme_css() + rules
