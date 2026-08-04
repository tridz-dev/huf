# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Render markdown documents to sanitized, print-ready HTML.

This is the first stage of the markdown -> {PDF, DOCX} pipeline. The HTML output
is consumed by downstream renderers (PDF and DOCX), so the output shape and
sanitization are critical for stability.
"""

import re

import markdown
import bleach

from huf.ai.artifacts.render.safety import (
	css_sanitizer,
	google_fonts_import,
	DEFAULT_BODY_FONT,
	DEFAULT_HEADING_FONT,
	DEFAULT_MONO_FONT,
)

#: Matches a Pandoc-style fenced div marking a multi-column region:
#:   :::columns-2
#:   ...markdown content...
#:   :::
#: There is no native markdown syntax for a "start/end" block region, so this
#: is a small custom convention, pre-processed BEFORE the main markdown pass
#: (the inner content is itself run through markdown.markdown() recursively,
#: so ordinary markdown still works inside a columns block).
COLUMNS_BLOCK_RE = re.compile(
	r"^:::columns-(2|3)\s*\n(.*?)\n:::\s*$",
	re.MULTILINE | re.DOTALL,
)


#: CSS stylesheet for print-ready HTML documents. Defines the selectors that
#: downstream PDF/DOCX renderers rely on. Includes paged-media syntax for
#: WeasyPrint and similar tools.
PRINT_STYLESHEET = """
__GOOGLE_FONTS_IMPORT__

body {
	font-family: __BODY_FONT__;
	font-size: 11pt;
	line-height: 1.6;
	color: #333;
}

h1, h2, h3, h4, h5, h6 {
	font-family: __HEADING_FONT__;
}

pre, code {
	font-family: __MONO_FONT__;
}

h1 {
	font-size: 28pt;
	font-weight: bold;
	margin-top: 1em;
	margin-bottom: 0.5em;
}

h2 {
	font-size: 22pt;
	font-weight: bold;
	margin-top: 0.9em;
	margin-bottom: 0.4em;
}

h3 {
	font-size: 18pt;
	font-weight: bold;
	margin-top: 0.8em;
	margin-bottom: 0.3em;
}

h4 {
	font-size: 14pt;
	font-weight: bold;
	margin-top: 0.7em;
	margin-bottom: 0.3em;
}

h5 {
	font-size: 12pt;
	font-weight: bold;
	margin-top: 0.6em;
	margin-bottom: 0.2em;
}

h6 {
	font-size: 11pt;
	font-weight: bold;
	margin-top: 0.5em;
	margin-bottom: 0.2em;
}

blockquote {
	border-left: 4px solid #999;
	font-style: italic;
	padding-left: 1em;
	margin-left: 0;
	margin-right: 0;
	color: #666;
}

table {
	border-collapse: collapse;
	width: 100%;
	margin: 1em 0;
}

th, td {
	border: 1px solid #444;
	padding: 6px;
	text-align: left;
}

th {
	font-weight: bold;
	background-color: #f5f5f5;
}

.text-left {
	text-align: left;
}

.text-center {
	text-align: center;
}

.text-right {
	text-align: right;
}

.indent-1 {
	margin-left: 0.5in;
}

.indent-2 {
	margin-left: 1in;
}

.indent-3 {
	margin-left: 1.5in;
}

.columns-2 {
	column-count: 2;
	column-gap: 1cm;
}

.columns-3 {
	column-count: 3;
	column-gap: 0.8cm;
}

@page {
	size: A4;
	margin: 2cm;
}

@page {
	@bottom-center {
		content: counter(page);
	}
}
"""

#: PRINT_STYLESHEET with the curated-font placeholders resolved. Kept as a
#: separate constant (rather than resolving inline at every call) since the
#: substitution only ever depends on the safety module's fixed defaults.
PRINT_STYLESHEET = (
	PRINT_STYLESHEET
	.replace("__GOOGLE_FONTS_IMPORT__", google_fonts_import())
	.replace("__BODY_FONT__", DEFAULT_BODY_FONT)
	.replace("__HEADING_FONT__", DEFAULT_HEADING_FONT)
	.replace("__MONO_FONT__", DEFAULT_MONO_FONT)
)


def _render_markdown(source: str) -> str:
	return markdown.markdown(
		source,
		extensions=["tables", "fenced_code", "attr_list", "sane_lists", "md_in_html"]
	)


def _expand_columns_blocks(markdown_source: str) -> str:
	"""Replace ``:::columns-N ... :::`` regions with their rendered
	``<div class="columns-N">...</div>`` HTML, so the surrounding markdown
	pass (which has no concept of this custom block syntax) never sees them.
	"""

	def _replace(match: re.Match) -> str:
		column_count = match.group(1)
		inner_markdown = match.group(2)
		inner_html = _render_markdown(inner_markdown)
		return f'<div class="columns-{column_count}">{inner_html}</div>'

	return COLUMNS_BLOCK_RE.sub(_replace, markdown_source)


#: Tags permitted through sanitization for BOTH the markdown and html paths.
ALLOWED_TAGS = [
	"p", "h1", "h2", "h3", "h4", "h5", "h6",
	"ul", "ol", "li",
	"table", "thead", "tbody", "tr", "th", "td",
	"blockquote",
	"strong", "em", "a", "img", "br", "hr",
	"pre", "code",
	"span", "div",
	"section", "aside", "header", "footer", "main",
	"figure", "figcaption", "small", "style",
]

#: Per-tag attribute allowances beyond the global set below.
_TAG_ALLOWED_ATTRIBUTES = {
	"a": ["href", "title"],
	"img": ["src", "alt"],
}

#: Attributes permitted on every tag.
_GLOBAL_ALLOWED_ATTRIBUTES = {"class", "id", "style"}


def _attribute_filter(tag: str, name: str, value: str) -> bool:
	"""bleach attribute-filter callable: global class/id/style, any data-*
	attribute (needed since the component stylesheet uses CSS
	``content: attr(data-label)``), plus each tag's own extra attributes.
	"""
	if name.startswith("data-"):
		return True
	if name in _GLOBAL_ALLOWED_ATTRIBUTES:
		return True
	return name in _TAG_ALLOWED_ATTRIBUTES.get(tag, [])


def render_document_html(markdown_source: str, title: str = "", language: str = "markdown") -> str:
	"""Render a document source to a full, sanitized, print-ready HTML document.

	Args:
		markdown_source: Document source text to render. Markdown by default;
			treated as raw HTML when ``language == "html"``.
		title: Optional title for the HTML document
		language: "markdown" (default) or "html". When "html", the source is
			sanitized and embedded directly - no markdown conversion runs.

	Returns:
		A complete HTML document string with sanitized content, ready for
		conversion to PDF or DOCX.
	"""
	if language == "html":
		html_body = markdown_source
	else:
		# Expand :::columns-N...::: regions first (they're pre-rendered to raw
		# HTML <div> markup), THEN run the rest of the source through markdown
		# normally. Markdown leaves embedded raw HTML block tags alone by
		# default, so the already-rendered <div> passes through untouched.
		preprocessed_source = _expand_columns_blocks(markdown_source)
		html_body = _render_markdown(preprocessed_source)

	# Sanitize the HTML to remove any dangerous content.
	#
	# css_sanitizer is required for inline style="..." to survive at all:
	# bleach drops the whole attribute unless one is supplied, which would
	# silently discard the agent's inline styling while <style> blocks kept
	# working. It also acts as a second filter, restricting inline CSS to
	# ALLOWED_CSS_PROPERTIES.
	sanitized_body = bleach.clean(
		html_body,
		tags=ALLOWED_TAGS,
		attributes=_attribute_filter,
		css_sanitizer=css_sanitizer(),
		strip=True
	)

	# Build the complete HTML document
	html_document = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{PRINT_STYLESHEET}
</style>
</head>
<body>
{sanitized_body}
</body>
</html>
"""

	return html_document
