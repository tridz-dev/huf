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
from huf.ai.artifacts.render.components import components_css

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
	color: var(--ink);
}

/* The @page box below sets the PRINT margin, but @page rules are print-media
   only - WeasyPrint honours them, but the in-chat/permalink preview renders
   this same HTML in a plain browser iframe, where @page is simply ignored.
   Without this, the preview's content sits flush against the iframe edges
   while the PDF looks correctly margined. Scoping the padding to @media
   screen gives the preview an equivalent margin WITHOUT adding to the PDF:
   WeasyPrint also renders "screen" as a media type it doesn't match against
   here (it's asked to print), so a bare `body { padding: 2cm }` outside this
   block would double the PDF margin to 4cm (2cm @page margin + 2cm padding).
   Keeping it inside @media screen is what keeps the two renders separate. */
@media screen {
	body {
		padding: 2cm;
		box-sizing: border-box;
	}

	/* `position: running(foot)` (components.py) only removes .doc-footer from
	   the flow in PAGED media. A browser ignores it entirely, so in the
	   preview iframe the element renders as ordinary in-flow content - and
	   because _hoist_running_footer() moves it to the very start of the body
	   (so the PDF repeats it on every page), it lands at the TOP of the
	   preview. Observed in the artifact pane: a document opened with
	   "CONFIDENTIAL - PAGE 1 OF 2" as its first line, above the letterhead.
	   The preview is one continuous scroll with no page boxes, so a per-page
	   footer has nothing to annotate there; hiding it keeps the preview
	   honest and leaves the PDF untouched.

	   !important is load-bearing, not laziness: an author's own <style>
	   block sits in the BODY, after this stylesheet, so at equal specificity
	   it wins the cascade (this is the same mechanism documented in
	   components.py). The document that surfaced this set
	   `.doc-footer { display: flex }`, which beat a plain `display: none`
	   here and left the footer visible at the top of the preview anyway.
	   Whether a running element is in flow is structural, not stylistic -
	   authors style the footer, they do not get to place it. */
	.doc-footer {
		display: none !important;
	}
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
	border-left: 4px solid var(--rule);
	font-style: italic;
	padding-left: 1em;
	margin-left: 0;
	margin-right: 0;
	color: var(--muted);
}

table {
	border-collapse: collapse;
	width: 100%;
	margin: 1em 0;
}

th, td {
	border: 1px solid var(--rule);
	padding: 6px;
	text-align: left;
}

th {
	font-weight: bold;
	background-color: var(--surface);
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

/* A single @page rule carries both the running footer (.doc-footer, pulled
   out of flow via `position: running(foot)` in components.py) and the page
   number. These are two separate margin boxes rather than one combined
   value because WeasyPrint's `content` property cannot concatenate an
   element() reference with a counter() - `content: element(foot) counter(page)`
   is not valid syntax, so the footer text and the page number each need
   their own @bottom-* box. Verified against WeasyPrint 68. */
@page {
	size: A4;
	margin: 2cm;

	@bottom-left {
		content: element(foot);
		font-size: 7.5pt;
		color: var(--muted);
	}

	@bottom-right {
		content: counter(page) " of " counter(pages);
		font-size: 7.5pt;
		color: var(--muted);
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

#: Component registry CSS (huf/ai/artifacts/render/components.py) is
#: appended after the base rules above so the PDF stylesheet and the
#: browser preview both render document components (doc-header, callout,
#: metric-grid, split, data-table, etc.) with the exact same CSS the DOCX
#: renderer's recipes are keyed against - one registry, not two drifting
#: definitions.
PRINT_STYLESHEET = PRINT_STYLESHEET + "\n" + components_css()


def _render_markdown(source: str) -> str:
	return markdown.markdown(
		source,
		extensions=["tables", "fenced_code", "attr_list", "sane_lists", "md_in_html"]
	)


def _strip_orphaned_class_markers(markdown_source: str) -> str:
	"""Remove `{: .class-name}` markers that are orphaned by a blank line.

	The attr_list extension requires NO blank line between content and its
	class marker, or the marker becomes literal text. Agents routinely add
	blank lines anyway. Rather than leaving stray `{: .text-center}` etc. in
	the rendered HTML, strip them here - the document reads fine without the
	alignment, and the alternative (leaving literal text) is worse.
	"""
	return re.sub(r"\n\n+(\{:\s+\.[a-z0-9_-]+(?:\s+\.[a-z0-9_-]+)*\s*\})", "", markdown_source)


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


#: Opening tag of any element carrying the ``doc-footer`` component class.
_DOC_FOOTER_OPEN_RE = re.compile(
	r"""<(?P<tag>[a-zA-Z][a-zA-Z0-9]*)\b[^>]*\bclass\s*=\s*["'][^"']*\bdoc-footer\b[^"']*["'][^>]*>""",
	re.IGNORECASE,
)

#: Any tag, used only to balance nesting while locating a footer's end tag.
_ANY_TAG_RE = re.compile(r"<(?P<closing>/?)(?P<tag>[a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(?P<selfclose>/?)>")

#: HTML void elements, which never have a matching close tag.
_VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})


def _hoist_running_footer(body_html: str) -> str:
	"""Move a ``.doc-footer`` element to the very start of the body.

	``.doc-footer`` is a CSS running element (``position: running(foot)`` in
	components.py), pulled into every page's bottom margin box by the @page
	rule above. But a running element only applies to the page it occurs on
	and every page AFTER it - that is how CSS GCPM defines it, and WeasyPrint
	68 implements it faithfully: a footer written at the END of a 27-page
	document appeared on page 27 alone.

	Authors write footers last, because that is where a footer visually
	belongs - the real agent-authored document that prompted this fix closed
	with its footer paragraph. Relying on the prompt to say "put the footer
	first" would be a rule the model has every reason to forget, and the
	failure is silent: the export looks fine on the last page and blank
	everywhere else.

	Hoisting is invisible in the output because the element is out of flow in
	any case, so moving it changes nothing except which pages it reaches.

	Bails out unchanged if the element cannot be located unambiguously
	(unbalanced markup, no footer present), since a wrong slice would corrupt
	the document - a footer on one page is a far smaller defect than mangled
	body HTML.
	"""
	match = _DOC_FOOTER_OPEN_RE.search(body_html)
	if not match:
		return body_html

	tag = match.group("tag").lower()

	if tag in _VOID_TAGS or match.group(0).rstrip().endswith("/>"):
		end = match.end()
	else:
		depth = 1
		end = None
		for candidate in _ANY_TAG_RE.finditer(body_html, match.end()):
			if candidate.group("tag").lower() != tag or candidate.group("selfclose"):
				continue
			depth += -1 if candidate.group("closing") else 1
			if depth == 0:
				end = candidate.end()
				break

		if end is None:
			# Unbalanced markup - leave the document exactly as authored.
			return body_html

	footer = body_html[match.start() : end]

	return footer + body_html[: match.start()] + body_html[end:]


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
		# Strip orphaned `{: .class-name}` markers that agents often separate
		# from their content by a blank line (causing attr_list to fail).
		# Then expand :::columns-N...::: regions (pre-rendered to raw HTML),
		# then run through markdown. Markdown leaves embedded raw HTML alone.
		cleaned_source = _strip_orphaned_class_markers(markdown_source)
		preprocessed_source = _expand_columns_blocks(cleaned_source)
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

	# Hoisted AFTER sanitization so the slice being moved is already known to
	# be well-formed, allowlisted markup rather than raw agent output.
	sanitized_body = _hoist_running_footer(sanitized_body)

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
