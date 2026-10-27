# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Render markdown documents to sanitized, print-ready HTML.

This is the first stage of the markdown -> {PDF, DOCX} pipeline. The HTML output
is consumed by downstream renderers (PDF and DOCX), so the output shape and
sanitization are critical for stability.
"""

import bisect
import html as _html
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
from huf.ai.artifacts.render import design_tokens as tokens
from huf.ai.artifacts.render.design_tokens import HEADING_SIZES_PT
from huf.ai.artifacts.render.components import components_css
from huf.ai.artifacts.render.screen_style import SCREEN_STYLESHEET

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
	font-size: __BODY_PT__pt;
	line-height: __BODY_LH__;
	color: var(--ink);
	background: #FFFFFF;
	-webkit-font-smoothing: antialiased;
	text-rendering: optimizeLegibility;
}

p {
	margin: 0 0 __PARA_PT__pt;
}

ul, ol {
	margin: 0 0 __PARA_PT__pt;
	padding-inline-start: __LIST_PT__pt;
}

li {
	margin: 0 0 2pt;
}

li > ul, li > ol {
	margin: 2pt 0 0;
}

li > p {
	margin: 0;
}

hr {
	border: none;
	border-top: 0.75pt solid var(--rule);
	margin: 14pt 0;
}

a {
	color: var(--accent);
	text-decoration: underline;
	text-underline-offset: 2px;
}

img {
	max-width: 100%;
	height: auto;
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
		/* An A4-width column, centred, so the in-app preview wraps at the
		   same measure as the PDF and the DOCX. Without it a wide preview
		   pane ran lines to 150+ characters. */
		max-width: 21cm;
		margin: 0 auto;
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

/* One sans family for every level - no serif display face. Hierarchy comes
   from weight and a compact size step, which keeps a long report calm. */
h1, h2, h3, h4, h5, h6 {
	font-family: __BODY_FONT__;
	line-height: __HEAD_LH__;
	color: var(--ink);
	letter-spacing: -0.005em;
	break-after: avoid;
	page-break-after: avoid;
}

h1 {
	letter-spacing: -0.01em;
}

h4, h5, h6 {
	color: var(--ink);
}

h6 {
	color: var(--muted);
}

pre, code {
	font-family: __MONO_FONT__;
	font-size: __CODE_PT__pt;
}

code {
	background-color: var(--surface);
	border: 0.5pt solid var(--rule);
	border-radius: 2pt;
	padding: 0 2pt;
}

pre {
	background-color: var(--surface);
	border: 0.75pt solid var(--rule);
	border-radius: 3pt;
	padding: 8pt 10pt;
	line-height: 1.45;
	white-space: pre-wrap;
	margin: 0 0 10pt;
}

pre code {
	border: none;
	padding: 0;
	background: none;
}

h1 {
	font-size: __H1_PT__pt;
	font-weight: __HW1__;
	margin-top: __H1_MT__pt;
	margin-bottom: __H1_MB__pt;
}

h2 {
	font-size: __H2_PT__pt;
	font-weight: __HW2__;
	margin-top: __H2_MT__pt;
	margin-bottom: __H2_MB__pt;
}

h3 {
	font-size: __H3_PT__pt;
	font-weight: __HW3__;
	margin-top: __H3_MT__pt;
	margin-bottom: __H3_MB__pt;
}

h4 {
	font-size: __H4_PT__pt;
	font-weight: __HW4__;
	margin-top: __H4_MT__pt;
	margin-bottom: __H4_MB__pt;
}

h5 {
	font-size: __H5_PT__pt;
	font-weight: __HW5__;
	margin-top: __H5_MT__pt;
	margin-bottom: __H5_MB__pt;
}

h6 {
	font-size: __H6_PT__pt;
	font-weight: __HW6__;
	margin-top: __H6_MT__pt;
	margin-bottom: __H6_MB__pt;
}

/* Quotes are a quiet aside, not a pull-quote: body size, muted, a thin
   rule. The old italic 4px-rule version read as oversized decoration. */
blockquote {
	border-inline-start: 2pt solid var(--rule);
	padding-block: 1pt;
	padding-inline: 10pt 0;
	margin: 0 0 10pt;
	color: var(--muted);
}

blockquote p:last-child {
	margin-bottom: 0;
}

/* Tables: compact, hairline rows, small caps-style header that does not
   wrap on two lines in an A4 column. */
table {
	border-collapse: collapse;
	width: 100%;
	margin: 6pt 0 12pt;
	font-size: __SMALL_PT__pt;
	line-height: 1.4;
	font-variant-numeric: tabular-nums;
}

th, td {
	border: none;
	border-bottom: 0.75pt solid var(--rule);
	padding-block: 4pt;
	padding-inline: 0 8pt;
	text-align: start;
	vertical-align: top;
}

th:last-child, td:last-child {
	padding-inline-end: 0;
}

th {
	font-size: __LABEL_PT__pt;
	font-weight: bold;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	color: var(--muted);
	border-bottom: 1pt solid var(--ink);
	vertical-align: bottom;
}

/* Arabic and other cursive scripts must not be letter-spaced: it breaks
   the joins between letters. */
:lang(ar) *, [dir="rtl"] *, [dir="auto"] * {
	letter-spacing: normal !important;
}

thead {
	display: table-header-group;
}

tr {
	break-inside: avoid;
	page-break-inside: avoid;
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
	margin-left: 0.25in;
}

.indent-2 {
	margin-left: 0.5in;
}

.indent-3 {
	margin-left: 0.75in;
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
		font-family: __BODY_FONT__;
		font-size: __CAPTION_PT__pt;
		color: var(--muted);
	}

	@bottom-right {
		content: counter(page) " of " counter(pages);
		font-family: __BODY_FONT__;
		font-size: __CAPTION_PT__pt;
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
	.replace("__BODY_PT__", str(tokens.BODY_SIZE_PT))
	.replace("__BODY_LH__", str(tokens.BODY_LINE_HEIGHT))
	.replace("__HEAD_LH__", str(tokens.HEADING_LINE_HEIGHT))
	.replace("__CODE_PT__", str(tokens.CODE_SIZE_PT))
	.replace("__SMALL_PT__", str(tokens.SMALL_SIZE_PT))
	.replace("__LABEL_PT__", str(tokens.LABEL_SIZE_PT))
	.replace("__CAPTION_PT__", str(tokens.CAPTION_SIZE_PT))
	.replace("__PARA_PT__", str(tokens.PARA_SPACE_AFTER_PT))
	.replace("__LIST_PT__", str(tokens.LIST_INDENT_PT))
	.replace("__H1_PT__", str(HEADING_SIZES_PT[1]))
	.replace("__H2_PT__", str(HEADING_SIZES_PT[2]))
	.replace("__H3_PT__", str(HEADING_SIZES_PT[3]))
	.replace("__H4_PT__", str(HEADING_SIZES_PT[4]))
	.replace("__H5_PT__", str(HEADING_SIZES_PT[5]))
	.replace("__H6_PT__", str(HEADING_SIZES_PT[6]))
	.replace("__H1_MT__", str(tokens.HEADING_SPACE_BEFORE_PT[1]))
	.replace("__H1_MB__", str(tokens.HEADING_SPACE_AFTER_PT[1]))
	.replace("__HW1__", "700")
	.replace("__H2_MT__", str(tokens.HEADING_SPACE_BEFORE_PT[2]))
	.replace("__H2_MB__", str(tokens.HEADING_SPACE_AFTER_PT[2]))
	.replace("__HW2__", "700")
	.replace("__H3_MT__", str(tokens.HEADING_SPACE_BEFORE_PT[3]))
	.replace("__H3_MB__", str(tokens.HEADING_SPACE_AFTER_PT[3]))
	.replace("__HW3__", "600")
	.replace("__H4_MT__", str(tokens.HEADING_SPACE_BEFORE_PT[4]))
	.replace("__H4_MB__", str(tokens.HEADING_SPACE_AFTER_PT[4]))
	.replace("__HW4__", "600")
	.replace("__H5_MT__", str(tokens.HEADING_SPACE_BEFORE_PT[5]))
	.replace("__H5_MB__", str(tokens.HEADING_SPACE_AFTER_PT[5]))
	.replace("__HW5__", "600")
	.replace("__H6_MT__", str(tokens.HEADING_SPACE_BEFORE_PT[6]))
	.replace("__H6_MB__", str(tokens.HEADING_SPACE_AFTER_PT[6]))
	.replace("__HW6__", "600")
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
	# Harmless inline presentational/phrasing tags (no extra attributes).
	"b", "i", "u", "s", "mark", "sub", "sup", "kbd", "abbr", "cite", "q", "wbr",
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


#: An HTML-mode document that opts into markdown inside a container.
_MARKDOWN_IN_HTML_RE = re.compile(r"""\bmarkdown\s*=\s*["']?1""", re.IGNORECASE)


#: Fenced code blocks (``` or ~~~, closed or running to EOF) and inline code
#: spans. Tags inside these are documentation, not structure, so the markdown
#: attribute scan must not see them.
_CODE_REGION_RE = re.compile(
	r"^[ \t]*(?P<fence>`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*(?P=fence)[`~]*[ \t]*$|\Z)|`[^`\n]+`",
	re.MULTILINE | re.DOTALL,
)

#: Opening tags that implicitly close an open <p>.
_CLOSES_P = frozenset({
	"p", "div", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6",
	"section", "aside", "header", "footer", "main", "pre", "blockquote",
	"figure", "hr",
})

#: Tag -> open tags it implicitly closes (HTML optional end tags).
_IMPLICIT_CLOSE = {
	"li": {"li"},
	"dt": {"dt", "dd"},
	"dd": {"dt", "dd"},
	"tr": {"tr", "td", "th"},
	"td": {"td", "th"},
	"th": {"td", "th"},
	"thead": {"tbody", "tr", "td", "th"},
	"tbody": {"thead", "tr", "td", "th"},
}
for _name in _CLOSES_P:
	_IMPLICIT_CLOSE.setdefault(_name, set()).add("p")
del _name


def _code_spans(source: str) -> list[tuple[int, int]]:
	return [(m.start(), m.end()) for m in _CODE_REGION_RE.finditer(source)]


def _in_spans(index: int, spans: list[tuple[int, int]]) -> bool:
	# Spans are sorted and non-overlapping (regex finditer order).
	i = bisect.bisect_right(spans, (index, float("inf"))) - 1
	return i >= 0 and spans[i][0] <= index < spans[i][1]


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
	"""Sort and merge overlapping ranges into disjoint sorted ones."""
	merged: list[tuple[int, int]] = []
	for lo, hi in sorted(ranges):
		if merged and lo <= merged[-1][1]:
			if hi > merged[-1][1]:
				merged[-1] = (merged[-1][0], hi)
		else:
			merged.append((lo, hi))
	return merged


def _iter_structural_tags(source: str):
	"""Yield (match, tag, kind) for real tags, skipping code regions.

	kind is "open", "close" or "void" (void or self-closing). Optional end
	tags (<p>, <li>, <td> ...) are closed implicitly by the next sibling
	opener, so they never linger on the caller's stack.
	"""
	spans = _merge_ranges(_code_spans(source) + _pre_regions(source))
	for match in _ANY_TAG_RE.finditer(source):
		if _in_spans(match.start(), spans):
			continue
		tag = match.group("tag").lower()
		if match.group("closing"):
			yield match, tag, "close"
		elif tag in _VOID_TAGS or match.group("selfclose"):
			yield match, tag, "void"
		else:
			yield match, tag, "open"


def _propagate_markdown_attr(source: str) -> str:
	"""Mark every ancestor of a ``markdown="1"`` container as markdown too.

	md_in_html treats a block element WITHOUT the attribute as an opaque raw
	HTML block, so a ``<section class="split-main" markdown="1">`` nested in a
	plain ``<div class="split">`` was never parsed - the documented pattern
	silently produced literal markdown. Only ancestors are marked; siblings
	such as the ``split-side`` aside stay raw HTML exactly as written.
	Tags inside code fences are ignored, ancestors that already carry the
	attribute are left alone, and implicitly closed tags (<p>, <li> ...) are
	popped so they never mark unrelated ancestors.
	"""
	stack: list[tuple[str, int, bool]] = []  # (tag, end index of open tag, has attr)
	marked_ends: set[int] = set()
	for match, tag, kind in _iter_structural_tags(source):
		if kind == "close":
			for index in range(len(stack) - 1, -1, -1):
				if stack[index][0] == tag:
					del stack[index:]
					break
			continue
		if kind == "void":
			continue
		closes = _IMPLICIT_CLOSE.get(tag)
		if closes:
			while stack and stack[-1][0] in closes:
				stack.pop()
		has_attr = bool(_MARKDOWN_IN_HTML_RE.search(match.group(0)))
		if has_attr:
			for _open_tag, open_end, open_has_attr in stack:
				if not open_has_attr:
					marked_ends.add(open_end)
		stack.append((tag, match.end(), has_attr))

	if not marked_ends:
		return source

	parts = []
	cursor = 0
	for open_end in sorted(marked_ends):
		# Insert just before the closing ">" of the ancestor's open tag.
		parts.append(source[cursor : open_end - 1])
		parts.append(' markdown="1"')
		cursor = open_end - 1
	parts.append(source[cursor:])
	return "".join(parts)


#: ``<pre>`` elements: their whitespace is content and must survive a dedent.
_PRE_OPEN_RE = re.compile(r"<pre(?=[\s>/])[^>]{0,2000}>", re.IGNORECASE)
_PRE_CLOSE_RE = re.compile(r"</pre(?=[\s>])\s*>", re.IGNORECASE)


def _pre_regions(source: str) -> list[tuple[int, int]]:
	"""(start, end) of each real <pre>...</pre>, skipping code fences and spans.

	A ``<pre`` mentioned in backticks or a fenced example is documentation, and
	an opener with no closing tag is literal text, not a region running to EOF.
	"""
	spans = _code_spans(source)
	regions: list[tuple[int, int]] = []
	pos = 0
	while True:
		opener = _PRE_OPEN_RE.search(source, pos)
		if not opener:
			break
		if _in_spans(opener.start(), spans) or opener.group(0).endswith("/>"):
			pos = opener.end()
			continue
		closer = _PRE_CLOSE_RE.search(source, opener.end())
		if not closer:
			# No </pre> anywhere after this opener, so none exists after any later opener either (linear scan).
			break
		regions.append((opener.start(), closer.end()))
		pos = closer.end()
	return regions


#: Most markdown="1" containers dedented per document; the rest are left as-is.
_MAX_DEDENT_CONTAINERS = 200


def _markdown_containers(source: str) -> list[tuple[int, int]]:
	"""(content start, close-tag start) of each closed markdown container, in document order.

	One tokenizing pass with a per-tag stack (same-name depth counting).
	"""
	stacks: dict[str, list[int | None]] = {}
	ranges: list[list[int]] = []
	for match, tag, kind in _iter_structural_tags(source):
		if kind == "void":
			continue
		if kind == "open":
			if _MARKDOWN_IN_HTML_RE.search(match.group(0)):
				ranges.append([match.end(), -1])
				stacks.setdefault(tag, []).append(len(ranges) - 1)
			else:
				stacks.setdefault(tag, []).append(None)
		else:
			stack = stacks.get(tag)
			if stack:
				idx = stack.pop()
				if idx is not None:
					ranges[idx][1] = match.start()
	return [(start, end) for start, end in ranges if end >= 0]


def _dedent_region(text: str):
	"""textwrap.dedent for a container, but <pre> / fenced interiors are left alone.

	Returns (new_text, mapper) where mapper converts an offset in text to the
	matching offset in new_text.
	"""
	lines = text.split("\n")
	starts = []
	pos = 0
	for line in lines:
		starts.append(pos)
		pos += len(line) + 1
	code_ranges: list[tuple[int, int]] = []
	for lo, hi in _pre_regions(text):
		code_ranges.append((lo, hi + 1))
	for match in _CODE_REGION_RE.finditer(text):
		fence = match.group("fence")
		if not fence:
			continue
		last_nl = text.rfind("\n", match.start(), match.end())
		closing = last_nl + 1
		if last_nl >= 0 and closing > match.start() and text[closing : match.end()].strip().startswith(fence[0] * len(fence)):
			code_ranges.append((match.start(), closing))
		else:
			code_ranges.append((match.start(), match.end() + 1))
	code_ranges = _merge_ranges(code_ranges)

	is_code = [_in_ranges(ls, code_ranges) for ls in starts]

	margin = None
	for n, (line, code) in enumerate(zip(lines, is_code)):
		# Text after the open tag shares line 0 with it: its indent is not the block's.
		if code or not line.strip(" \t") or n == 0:
			continue
		indent = line[: len(line) - len(line.lstrip(" \t"))]
		if margin is None:
			margin = indent
		else:
			common = 0
			for x, y in zip(margin, indent):
				if x != y:
					break
				common += 1
			margin = margin[:common]
	margin = margin or ""

	out = []
	removed = []
	for n, (line, code) in enumerate(zip(lines, is_code)):
		if code or (n == 0 and line.strip(" \t")):
			out.append(line)
			removed.append(0)
		elif not line.strip(" \t"):
			out.append("")
			removed.append(len(line))
		elif margin and line.startswith(margin):
			out.append(line[len(margin) :])
			removed.append(len(margin))
		else:
			out.append(line)
			removed.append(0)
	new_starts = []
	pos = 0
	for line in out:
		new_starts.append(pos)
		pos += len(line) + 1
	new_text = "\n".join(out)

	def mapper(offset: int) -> int:
		if offset >= len(text):
			return len(new_text)
		i = bisect.bisect_right(starts, offset) - 1
		return new_starts[i] + max(0, offset - starts[i] - removed[i])

	return new_text, mapper


def _in_ranges(index: int, ranges: list[tuple[int, int]]) -> bool:
	# ranges must be sorted and disjoint (see _merge_ranges).
	i = bisect.bisect_left(ranges, (index,)) - 1
	return i >= 0 and ranges[i][0] < index < ranges[i][1]


def _dedent_markdown_containers(source: str) -> str:
	"""Strip the common leading indent from each ``markdown="1"`` container.

	Pretty-printed HTML indents children by 4+ spaces, which markdown reads
	as an indented code block (<pre><code>). Removing the indent shared by the
	container's lines keeps relative nesting but lets headings, tables and
	lists parse as markdown. <pre> and fenced-code interiors are untouched.

	The source is tokenized once; containers are dedented outermost first
	(an outer container must see its children's original indent) and the
	remaining ranges are remapped after each edit. Past
	_MAX_DEDENT_CONTAINERS containers the rest are left as written.
	"""
	ranges = [list(r) for r in _markdown_containers(source)[:_MAX_DEDENT_CONTAINERS]]
	for i in range(len(ranges)):
		start, end = ranges[i]
		region = source[start:end]
		new_region, mapper = _dedent_region(region)
		if new_region == region:
			continue
		delta = len(new_region) - len(region)
		source = source[:start] + new_region + source[end:]
		for other in ranges[i + 1 :]:
			if other[0] >= end:
				other[0] += delta
				other[1] += delta
			else:
				other[0] = start + mapper(other[0] - start)
				other[1] = start + mapper(other[1] - start)
	return source


#: Block containers whose raw text is worth parsing as markdown when it clearly is markdown.
_MARKDOWN_CONTAINER_TAGS = frozenset({"div", "section", "aside", "article", "main", "blockquote", "figure"})

#: Raw markdown block syntax (heading, list item, table row, bold) sitting in container text.
_LEAKY_MARKDOWN_RE = re.compile(
	r"^[ \t]*(?:#{1,6}[ \t]+\S|[-*+][ \t]+\S|\d+[.)][ \t]+\S|\|.+\|[ \t]*$)|\*\*\S(?:[^*\n]*\S)?\*\*",
	re.MULTILINE,
)


def _mark_unmarked_markdown_containers(source: str) -> str:
	"""Add ``markdown="1"`` to block containers whose own text is raw markdown.

	Authors (and models) routinely write ``<div class="x">## Title\n- item</div>``
	without the attribute; md_in_html then leaves the text literal. Only the
	direct text of a container counts (text inside <p>/<li>/<td> is left alone),
	code regions are ignored, and containers already marked are skipped.
	"""
	spans = _merge_ranges(_code_spans(source) + _pre_regions(source))
	stack: list[tuple[str, int, bool]] = []  # (tag, end of open tag, already marked)
	marked_ends: set[int] = set()
	previous_end = 0

	def check_gap(start: int, end: int) -> None:
		if not stack or end <= start:
			return
		tag, open_end, has_attr = stack[-1]
		if has_attr or tag not in _MARKDOWN_CONTAINER_TAGS or open_end in marked_ends:
			return
		chars = list(source[start:end])
		for lo, hi in spans:
			for i in range(max(lo, start), min(hi, end)):
				chars[i - start] = " "
		if _LEAKY_MARKDOWN_RE.search("".join(chars)):
			marked_ends.add(open_end)

	for match, tag, kind in _iter_structural_tags(source):
		check_gap(previous_end, match.start())
		previous_end = match.end()
		if kind == "close":
			for index in range(len(stack) - 1, -1, -1):
				if stack[index][0] == tag:
					del stack[index:]
					break
			continue
		if kind == "void":
			continue
		closes = _IMPLICIT_CLOSE.get(tag)
		if closes:
			while stack and stack[-1][0] in closes:
				stack.pop()
		stack.append((tag, match.end(), bool(_MARKDOWN_IN_HTML_RE.search(match.group(0)))))
	if not marked_ends:
		return source
	parts = []
	cursor = 0
	for open_end in sorted(marked_ends):
		parts.append(source[cursor : open_end - 1])
		parts.append(' markdown="1"')
		cursor = open_end - 1
	parts.append(source[cursor:])
	return "".join(parts)


_LIST_ITEM_LINE_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\S")
_FENCE_LINE_RE = re.compile(r"^[ \t]*(?:`{3,}|~{3,})")


def _separate_glued_lists(source: str) -> str:
	"""Insert a blank line between a paragraph line and a list that follows it directly.

	Python-Markdown only starts a list after a blank line, so ``text\n* item``
	rendered the bullet as literal text inside the paragraph.
	"""
	out: list[str] = []
	in_fence = False
	prev = ""
	for line in source.split("\n"):
		if _FENCE_LINE_RE.match(line):
			in_fence = not in_fence
		elif (
			not in_fence
			and _LIST_ITEM_LINE_RE.match(line)
			and prev.strip()
			and not _LIST_ITEM_LINE_RE.match(prev)
			and not prev.startswith((" ", "\t"))
			and not prev.lstrip().startswith(("<", "|", "#"))
		):
			out.append("")
		out.append(line)
		prev = line
	return "\n".join(out)


_TASK_ITEM_RE = re.compile(r"(<li>\s*)\[( |x|X)\](?=\s)")


def _render_task_items(html_body: str) -> str:
	"""GFM task-list markers have no markdown extension here; show them as checkbox glyphs."""
	return _TASK_ITEM_RE.sub(lambda m: m.group(1) + ("\u2610" if m.group(2) == " " else "\u2611"), html_body)


def _prepare_markdown_in_html(source: str) -> str:
	"""Opt-in/implicit markdown-inside-HTML preprocessing shared by both languages."""
	source = _mark_unmarked_markdown_containers(source)
	if not _MARKDOWN_IN_HTML_RE.search(source):
		return source
	return _separate_glued_lists(_dedent_markdown_containers(_propagate_markdown_attr(source)))


_STYLE_BLOCK_RE = re.compile(r"(<style\b[^>]*>)(.*?)(</style\s*>)", re.IGNORECASE | re.DOTALL)
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_IMPORT_RE = re.compile(r"@import\b[^;{}]*(;|(?=[}\n]|$))", re.IGNORECASE)
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)\s*([^)]*?)\s*\1\s*\)", re.IGNORECASE)
_CSS_DANGEROUS_RE = re.compile(
	r"expression\s*\([^;}]*\)?|behaviou?r\s*:[^;}]*|-moz-binding\s*:[^;}]*|javascript\s*:",
	re.IGNORECASE,
)


_CSS_ESCAPE_RE = re.compile(r"\\([0-9a-fA-F]{1,6})\s?|\\(.)", re.DOTALL)
_CSS_REMOTE_FUNC_RE = re.compile(r"(?:image-set|-webkit-image-set|cross-fade|element|src)\s*\([^)]*\)", re.IGNORECASE)


def _decode_css_escapes(css: str) -> str:
	def _sub(m):
		if m.group(1):
			try:
				cp = int(m.group(1), 16)
				return chr(cp) if 0 < cp <= 0x10FFFF else ""
			except ValueError:
				return ""
		return m.group(2) if m.group(2) != "\n" else ""

	return _CSS_ESCAPE_RE.sub(_sub, css)


def _strip_remote_css(css: str) -> str:
	css = _CSS_REMOTE_FUNC_RE.sub("none", css)
	css = _CSS_IMPORT_RE.sub("", css)

	def _url(match):
		target = match.group(2).strip().lower()
		if target.startswith(("#", "/")) and not target.startswith("//"):
			return match.group(0)
		if re.match(r"^[a-z0-9_./~-][^:]*$", target) and not target.startswith("//"):
			return match.group(0)
		return "none"

	css = _CSS_URL_RE.sub(_url, css)
	return _CSS_DANGEROUS_RE.sub("", css)


def _sanitize_css(css: str) -> str:
	"""Strip remote/exfiltrating constructs from author CSS, keep local CSS.

	CSS escapes (`u\\72l(`, `@\\69mport`) are decoded only to *detect* hidden constructs. When the decoded form
	is clean the original text is kept verbatim (so `content:"\\A"` keeps working); when decoding revealed
	something, the stripped decoded form is emitted instead, with `<`, `>` and `\\` re-escaped so decoded text can
	never close the <style> element.
	"""
	css = _CSS_COMMENT_RE.sub("", css)
	decoded = _decode_css_escapes(css)
	stripped_decoded = _strip_remote_css(decoded)
	if stripped_decoded == decoded:
		out = _strip_remote_css(css)
	else:
		out = stripped_decoded.replace("\\", "\\5c ").replace("<", "\\3c ").replace(">", "\\3e ")
	return out.replace("<", "\\3c ")


def _sanitize_style_blocks(html_body: str) -> str:
	"""bleach keeps <style> text verbatim, so scrub its CSS here."""
	return _STYLE_BLOCK_RE.sub(
		lambda m: m.group(1) + _sanitize_css(m.group(2)) + m.group(3), html_body
	)


def sanitize_html(html_body: str) -> str:
	"""Run the pipeline's bleach configuration over an HTML fragment.

	css_sanitizer is required for inline style="..." to survive at all:
	bleach drops the whole attribute unless one is supplied, which would
	silently discard the agent's inline styling while <style> blocks kept
	working. It also acts as a second filter, restricting inline CSS to
	ALLOWED_CSS_PROPERTIES.
	"""
	cleaned = bleach.clean(
		html_body,
		tags=ALLOWED_TAGS,
		attributes=_attribute_filter,
		css_sanitizer=css_sanitizer(),
		strip=True,
	)
	return _sanitize_style_blocks(cleaned)


def render_document_html(markdown_source: str, title: str = "", language: str = "markdown") -> str:
	"""Render a document (see ``render_document_html_with_report``) and return only the HTML."""
	html_document, report = render_document_html_with_report(markdown_source, title, language)
	if report["leaks_found"] or report["fallback_used"]:
		try:
			import frappe

			frappe.logger("huf.document").warning(
				"markdown leak guard: found=%s repaired=%s remaining=%s fallback=%s kinds=%s",
				report["leaks_found"], report["repaired"], report["leaks_remaining"], report["fallback_used"], ",".join(report["kinds"]),
			)
		except Exception:
			pass
	return html_document


def render_document_html_with_report(markdown_source: str, title: str = "", language: str = "markdown"):
	"""Render a document source to a full, sanitized, print-ready HTML document.

	Args:
		markdown_source: Document source text to render. Markdown by default;
			treated as raw HTML when ``language == "html"``.
		title: Optional title for the HTML document
		language: "markdown" (default) or "html". When "html", the source is
			sanitized and embedded directly - no markdown conversion runs.

	Returns:
		``(html_document, report)``; report has ``leaks_found``, ``repaired``,
		``leaks_remaining`` (counts) and ``kinds`` (sorted leak kinds found).
	"""
	from huf.ai.artifacts.render.markdown_guard import (
		convert_task_markers,
		enable_markdown_in_containers,
		find_markdown_leaks,
		repair_markdown_leaks,
		fallback_markdown_leaks,
	)
	from huf.ai.artifacts.render.markdown_normalize import normalize_markdown_blocks

	if language == "html":
		# Containers holding markdown get markdown="1" (explicit ones are propagated
		# and dedented first); sources with no such container are untouched.
		prepared = _prepare_markdown_in_html(markdown_source)
		annotated = enable_markdown_in_containers(prepared)
		html_body = (
			_render_task_items(
				_render_markdown(
					convert_task_markers(normalize_markdown_blocks(_strip_orphaned_class_markers(annotated)))
				)
			)
			if annotated != markdown_source
			else markdown_source
		)
	else:
		# Strip orphaned `{: .class-name}` markers that agents often separate
		# from their content by a blank line (causing attr_list to fail).
		# Then expand :::columns-N...::: regions (pre-rendered to raw HTML),
		# then run through markdown. Markdown leaves embedded raw HTML alone.
		cleaned_source = normalize_markdown_blocks(
			_strip_orphaned_class_markers(_prepare_markdown_in_html(markdown_source))
		)
		preprocessed_source = _expand_columns_blocks(convert_task_markers(enable_markdown_in_containers(cleaned_source)))
		html_body = _render_task_items(_render_markdown(preprocessed_source))

	# Sanitize the HTML to remove any dangerous content (see sanitize_html).
	sanitized_body = sanitize_html(html_body)

	# Safety net: detect residual markdown in the sanitized output and repair.
	leaks = find_markdown_leaks(sanitized_body)
	repaired = 0
	remaining = 0
	if leaks:
		sanitized_body, repaired = repair_markdown_leaks(sanitized_body)
		remaining = len(find_markdown_leaks(sanitized_body))
	fallback_used = 0
	if remaining:
		sanitized_body, fallback_used = fallback_markdown_leaks(sanitized_body)
		remaining = len(find_markdown_leaks(sanitized_body))
	report = {
		"fallback_used": fallback_used,
		"leaks_found": len(leaks),
		"repaired": repaired,
		"leaks_remaining": remaining,
		"kinds": sorted({lk.kind for lk in leaks}),
	}

	# Hoisted AFTER sanitization so the slice being moved is already known to
	# be well-formed, allowlisted markup rather than raw agent output.
	sanitized_body = _hoist_running_footer(sanitized_body)

	# Build the complete HTML document
	html_document = f"""<!DOCTYPE html>
<html dir="auto">
<head>
<meta charset="utf-8">
<title>{_html.escape(str(title or ''), quote=True)}</title>
<style>
{PRINT_STYLESHEET}
{SCREEN_STYLESHEET}
</style>
</head>
<body dir="auto">
{sanitized_body}
</body>
</html>
"""

	return html_document, report
