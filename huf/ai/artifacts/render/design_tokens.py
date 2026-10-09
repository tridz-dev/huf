# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""The one design system every document format is drawn from.

The HTML (and so the PDF and the in-app Document view) and the DOCX used to
pick their own fonts and sizes, so the same markdown looked different in each.
Both now read this module: a family is named once, and each format resolves it
to the face it can actually draw.

Word has no CSS fallback chain and does not have Google Fonts, so the
canonical faces are ones Word, macOS and Google Docs all ship (Arial,
Courier New). The whole document is ONE sans family: titles, headings, body,
KPI values and the brand all use it, and hierarchy comes from weight rather
than from a second (serif) display face. A serif title read as dated and
fought the compact scale below. The stack is Arial then the metric-compatible
Arimo / Liberation Sans, so PDF line breaks match the DOCX (Arial) exactly;
no proportionally different face (Inter, system UI) is ever preferred.
Every size token is a multiple of 0.5pt because Word stores half-points.
"""

_SANS_STACK = (
	"'Arial', 'Arimo', 'Liberation Sans', 'Helvetica Neue', 'DejaVu Sans', sans-serif"
)

#: role -> (canonical family the DOCX names, CSS stack the HTML/PDF uses)
FONT_ROLES = {
	"body": ("Arial", _SANS_STACK),
	# Same face as the body on purpose - there is no display font.
	"heading": ("Arial", _SANS_STACK),
	"mono": (
		"Courier New",
		"'Courier New', 'Cousine', 'Liberation Mono', 'DejaVu Sans Mono', monospace",
	),
}

#: Google Fonts specs for the metric-compatible webfonts named above.
METRIC_WEBFONTS = {
	"Arimo": "Arimo:wght@400;700",
	"Cousine": "Cousine:wght@400;700",
}

BODY_FONT = FONT_ROLES["body"][0]
HEADING_FONT = FONT_ROLES["heading"][0]
MONO_FONT = FONT_ROLES["mono"][0]

BODY_STACK = FONT_ROLES["body"][1]
HEADING_STACK = FONT_ROLES["heading"][1]
MONO_STACK = FONT_ROLES["mono"][1]

#: Type scale in points (1pt = 1.333 CSS px at 96 dpi), tuned for an A4 page
#: shown at 794px. Hierarchy is carried by weight, not size:
#:
#:   title / h1  19.5pt  26px      h4      10pt   13.3px
#:   h2          13pt    17.3px    body    9.5pt  12.7px (line-height 1.55)
#:   h3          11pt    14.7px    table   9pt    12px
#:   caption/meta 8.5pt  11.3px     badge   7.5pt  10px
#:
#: The previous scale (title 22 / h2 15 / h3 12 / body 10.5pt) still read
#: big at A4 width in the preview.
HEADING_SIZES_PT = {1: 19.5, 2: 13, 3: 11, 4: 10, 5: 9.5, 6: 9.5}
BODY_SIZE_PT = 9.5
CODE_SIZE_PT = 8.5
#: Secondary text: table cells, subtitles of cards.
SMALL_SIZE_PT = 9
#: Captions, meta, brand line, footer.
CAPTION_SIZE_PT = 8.5
#: Labels: table headers, metric labels, badges, sidebar headings.
LABEL_SIZE_PT = 7.5
#: Document title (.doc-title) and standfirst (.doc-subtitle).
TITLE_SIZE_PT = 19.5
SUBTITLE_SIZE_PT = 11
#: KPI value inside a .metric card.
METRIC_VALUE_SIZE_PT = 13.5
#: Sidebar (.split-side) body text: 12.5px.
SIDE_SIZE_PT = 9.5
#: Sidebar list indent (~14px).
SIDE_LIST_INDENT_PT = 10.5
#: Sidebar geometry (CSS px): the aside never gets narrower than
#: SIDE_MIN_WIDTH_PX, and the main column never narrower than
#: MAIN_MIN_WIDTH_PX - when both cannot fit, the aside stacks below.
SIDE_MIN_WIDTH_PX = 240
MAIN_MIN_WIDTH_PX = 420

#: Unitless CSS line-heights. Word's "multiple" spacing is measured against
#: the font's own line gap (about 1.15x the em for Arial), so the DOCX uses
#: the smaller multiplier to land on the same visual rhythm.
BODY_LINE_HEIGHT = 1.55
HEADING_LINE_HEIGHT = 1.25
DOCX_BODY_LINE_SPACING = 1.3
DOCX_HEADING_LINE_SPACING = 1.1

#: Space before each heading, and the shared paragraph rhythm, in points.
HEADING_SPACE_BEFORE_PT = {1: 12, 2: 14, 3: 10, 4: 8, 5: 6, 6: 6}
HEADING_SPACE_AFTER_PT = {1: 6, 2: 5, 3: 4, 4: 3, 5: 2, 6: 2}
PARA_SPACE_AFTER_PT = 6
#: List indent (left padding of ul/ol), in points.
LIST_INDENT_PT = 13.5
