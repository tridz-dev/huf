# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""The one design system every document format is drawn from.

The HTML (and so the PDF and the in-app Document view) and the DOCX used to
pick their own fonts and sizes, so the same markdown looked different in each.
Both now read this module: a family is named once, and each format resolves it
to the face it can actually draw.

Word has no CSS fallback chain and does not have Google Fonts, so the canonical
faces are the ones Word, macOS and Google Docs all ship (Arial, Georgia,
Courier New). The HTML stacks name the same face first and then a
metric-compatible webfont (Arimo, Gelasio, Cousine), so a server without
Arial still lays out to the same line breaks as Word.
"""

#: role -> (canonical family the DOCX names, CSS stack the HTML/PDF uses)
FONT_ROLES = {
	"body": (
		"Arial",
		"'Arial', 'Arimo', 'Liberation Sans', 'DejaVu Sans', sans-serif",
	),
	"heading": (
		"Georgia",
		"'Georgia', 'Gelasio', 'DejaVu Serif', serif",
	),
	"mono": (
		"Courier New",
		"'Courier New', 'Cousine', 'Liberation Mono', 'DejaVu Sans Mono', monospace",
	),
}

#: Google Fonts specs for the metric-compatible webfonts named above.
METRIC_WEBFONTS = {
	"Arimo": "Arimo:wght@400;700",
	"Gelasio": "Gelasio:wght@400;700",
	"Cousine": "Cousine:wght@400;700",
}

BODY_FONT = FONT_ROLES["body"][0]
HEADING_FONT = FONT_ROLES["heading"][0]
MONO_FONT = FONT_ROLES["mono"][0]

BODY_STACK = FONT_ROLES["body"][1]
HEADING_STACK = FONT_ROLES["heading"][1]
MONO_STACK = FONT_ROLES["mono"][1]

#: Type scale in points, h1..h6, and the body size.
HEADING_SIZES_PT = {1: 28, 2: 22, 3: 18, 4: 14, 5: 12, 6: 11}
BODY_SIZE_PT = 11
CODE_SIZE_PT = 9.5

#: Space before each heading, and the shared paragraph rhythm, in points.
HEADING_SPACE_BEFORE_PT = {1: 14, 2: 14, 3: 12, 4: 10, 5: 8, 6: 6}
PARA_SPACE_AFTER_PT = 6
