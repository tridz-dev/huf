# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Convert the HTML produced by ``render_document_html`` into a .docx file.

This is the second stage of the markdown -> {PDF, DOCX} pipeline. The HTML
contract is defined and enforced by ``huf.ai.artifacts.render.html`` — this
module does not accept arbitrary HTML, only the specific tag/class
vocabulary that ``render_document_html`` produces:

- Block tags: p, h1-h6, ul, ol, li, table, thead, tbody, tr, th, td,
  blockquote, hr, pre
- Inline tags: strong, em, a, img, br, code, span, div
- Alignment via class="text-left|text-center|text-right" on a block element
- Indent via class="indent-1|indent-2|indent-3" on a block element
- Document components (doc-header, callout, metric-grid, split, data-table,
  etc.) via a class from ``huf.ai.artifacts.render.components.COMPONENTS`` —
  see the "Component dispatch" section below.

The HTML is walked with the stdlib ``html.parser.HTMLParser`` (not
BeautifulSoup) to keep this module dependency-free beyond python-docx.

Component dispatch
-------------------
``COMPONENTS`` (huf/ai/artifacts/render/components.py) is the single source
of truth for what a component class means in DOCX terms — every entry's
"docx" key is a data recipe, not code, so this module is an INTERPRETER for
those recipes rather than a second definition of what "doc-header" or
"callout" looks like. Rendering functions below accept a ``container``
(either the top-level ``Document`` or a table ``_Cell``) rather than always
a ``Document``, since python-docx's ``Document`` and ``_Cell`` both expose
``add_paragraph``/``add_table`` — this lets component recipes nest (e.g. a
callout's children, or a split cell's content) using the exact same
rendering functions as the top level.
"""

import base64
import io
import re
from html.parser import HTMLParser

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from huf.ai.artifacts.render import design_tokens as tokens
from docx.shared import Cm, Emu, Inches, Pt, RGBColor

from huf.ai.artifacts.render.components import COMPONENTS, COMPONENT_CLASSES, SAFE_DEFAULT_COLOR, THEME, resolve_theme_token


#: Maps a block element's alignment class to a python-docx alignment constant.
_ALIGNMENTS = {
	"text-left": WD_ALIGN_PARAGRAPH.LEFT,
	"text-center": WD_ALIGN_PARAGRAPH.CENTER,
	"text-right": WD_ALIGN_PARAGRAPH.RIGHT,
}

#: Maps a block element's indent class to an indent level (in half-inches).
_INDENTS = {
	"indent-1": 1,
	"indent-2": 2,
	"indent-3": 3,
}

#: Fallback content width (A4, 2cm margins - 21cm - 4cm = 17cm), used only if
#: a table is ever built without the real value threaded through
#: theme["_content_width_emu"] (see html_to_docx / _document_content_width_emu).
#: html_to_docx always sets that key before rendering anything, so this is a
#: defensive last resort, not the normal path - the normal path reads the
#: Document's actual section geometry rather than hardcoding a page size.
_FALLBACK_CONTENT_WIDTH_EMU = Cm(17)

#: Block-level tags that terminate the "current" node when closed. Everything
#: else (inline tags, and stray tags outside the sanitized vocabulary) is
#: treated as text-bearing but does not open a new node in the tree, UNLESS
#: it carries a registry component class — see ``_opens_node``.
_BLOCK_TAGS = {
	"p", "h1", "h2", "h3", "h4", "h5", "h6",
	"ul", "ol", "li",
	"table", "thead", "tbody", "tr", "th", "td",
	"blockquote", "hr", "pre",
	"div",
}

#: Container tags whose children must each render as their own separate docx
#: block, never flattened into a single joined string via full_text. div is
#: only ever used by render_document_html for a columns-N section wrapper (or
#: a document component) - a structural container, not a text-bearing leaf
#: like p/blockquote.
_CONTAINER_TAGS = ("table", "thead", "tbody", "tr", "th", "td", "div")

#: Tags whose text (and descendant text) should be dropped from the parent's
#: rendered text rather than concatenated inline. None of the tags in the
#: sanitized vocabulary need this, but "script"/"style" are excluded
#: defensively in case they ever slip through. "style" text is not simply
#: discarded, though - see _BodyTreeBuilder.style_text_parts - an author's
#: <style> block is the only place a re-themed document's colours live, and a
#: document that redefined --accent etc. in a <style> block used to export
#: with the registry's hardcoded default palette because this text never
#: reached anything past the parser. Keeping it OUT of the body (so it never
#: leaks as literal paragraph text - that part already worked) while ALSO
#: capturing it separately is what lets html_to_docx() parse the author's
#: :root overrides and recolour every recipe to match.
_IGNORED_TEXT_TAGS = {"script", "style"}


class _InlineFormat(tuple):
	"""(bold, italic, code, href, line_break) for one run of text. A tuple so
	it is hashable and cheap; built only by _BodyTreeBuilder."""

	__slots__ = ()

	def __new__(cls, bold=False, italic=False, code=False, href="", line_break=False):
		return super().__new__(cls, (bold, italic, code, href, line_break))

	bold = property(lambda self: self[0])
	italic = property(lambda self: self[1])
	code = property(lambda self: self[2])
	href = property(lambda self: self[3])
	line_break = property(lambda self: self[4])


_PLAIN = _InlineFormat()

#: Inline tags that change how their text is written (they never open a node
#: unless they also carry a component class).
_INLINE_FORMAT_TAGS = {"strong", "b", "em", "i", "code", "a"}


class _Node:
	"""A single element in the simplified DOM tree built from the HTML body."""

	def __init__(self, tag: str, attrs: dict[str, str], parent: "_Node | None" = None):
		self.tag = tag
		self.attrs = attrs
		self.parent = parent
		self.children: list["_Node"] = []
		#: Accumulated text for this node, used for leaf-like elements (p, h1-h6,
		#: li, th, td, blockquote). Container elements (table, tr, ul, ol) only
		#: use ``children``.
		self.text_parts: list[str] = []
		#: Text and child nodes in the exact order the parser encountered
		#: them - ("text", str) or ("node", _Node). text_parts/children above
		#: are each flattened views of this (kept for the existing code that
		#: only needs one or the other); this is what _all_descendant_text
		#: needs to reconstruct real document order across a mix of bare text
		#: and nested elements, e.g. "<strong>Label:</strong> tail text".
		#: The third element is the inline format a text part was written in
		#: (see _InlineFormat) - None for a child node. It is what lets
		#: paragraphs keep bold/italic/code/links as real Word runs instead
		#: of flattening them to plain text.
		self._ordered_parts: list[tuple[str, "str | _Node", "_InlineFormat | None"]] = []

	def add_text(self, data: str, fmt: "_InlineFormat | None" = None) -> None:
		self.text_parts.append(data)
		self._ordered_parts.append(("text", data, fmt or _PLAIN))

	def add_child(self, child: "_Node") -> None:
		self.children.append(child)
		self._ordered_parts.append(("node", child, None))

	@property
	def text(self) -> str:
		return "".join(self.text_parts).strip()

	def classes(self) -> set[str]:
		class_attr = self.attrs.get("class") or ""
		return set(class_attr.split())

	@property
	def full_text(self) -> str:
		"""Own text plus the text of any nested block children, joined by
		newlines. Markdown wraps blockquote (and sometimes list item) content
		in a nested ``<p>``, so a node's directly-owned text alone can miss
		that content — this walks block descendants to recover it.
		"""
		parts = [self.text] if self.text else []
		for child in self.children:
			if child.tag in _BLOCK_TAGS and child.tag not in _CONTAINER_TAGS:
				child_text = child.full_text
				if child_text:
					parts.append(child_text)
		return "\n".join(parts)


def _all_descendant_text(node: "_Node") -> str:
	"""Every bit of text under ``node``, in true document order, regardless
	of tag - unlike ``full_text`` (which only walks ``_BLOCK_TAGS`` minus
	``_CONTAINER_TAGS``, deliberately excluding div/table/td/etc.), this
	walks EVERY child node.

	Needed because ``div`` is both a ``_BLOCK_TAG`` and a ``_CONTAINER_TAG``:
	a value wrapped in a child div - e.g.
	``<div class="metric" data-label="X"><div class="metric-value">$12.5M</div></div>``
	- puts "$12.5M" on the *child* node, and ``full_text`` skips container
	children on purpose, so the value silently disappeared even though
	``full_text`` looked like the obvious thing to reach for. Observed in
	production: a metric card exported with its label but no value.

	Walks ``_ordered_parts`` rather than ``text_parts``/``children``
	separately so text that comes before/after a nested element - e.g.
	``<strong>Label:</strong> tail text`` - is reassembled in the order it
	was written rather than all-text-then-all-children.
	"""
	segments = []
	for kind, value, _fmt in node._ordered_parts:
		if kind == "text":
			segments.append(value)
		elif value.tag != "img":
			segments.append(_all_descendant_text(value))
	return "".join(segments).strip()


def _opens_node(tag: str, attrs: dict[str, str]) -> bool:
	"""Whether a start tag should open a new ``_Node`` and become the
	parser's "current" element.

	True for the fixed block-tag vocabulary (unchanged from before), and
	ALSO true for any tag carrying a registry component class (e.g. a
	``<span class="brand">``) — components can be authored on inline tags
	that would otherwise just fold their text into the enclosing block, and
	the DOCX walker needs a real node to dispatch the recipe against. This
	reads from ``COMPONENT_CLASSES`` rather than hardcoding tag names, so a
	future component class works regardless of which tag it's applied to.
	"""
	if tag in _BLOCK_TAGS:
		return True
	classes = set((attrs.get("class") or "").split())
	return bool(classes & COMPONENT_CLASSES)


class _BodyTreeBuilder(HTMLParser):
	"""Builds a simplified tree of ``_Node`` objects from the sanitized HTML body.

	Only tags reach this parser that were already allowed through
	``render_document_html``'s bleach sanitization, so no further validation
	of the tag/attribute vocabulary is performed here.
	"""

	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.root = _Node("root", {})
		self._current = self.root
		self._ignored_depth = 0
		#: Which _IGNORED_TEXT_TAGS tag is currently suppressing body text, as
		#: a stack rather than a single name - handle_endtag needs to know
		#: which tag is closing even though script/style never nest in
		#: practice, so a stack costs nothing and avoids a latent bug if they
		#: ever did.
		self._ignored_tag_stack: list[str] = []
		#: Raw text found inside <style> tags, kept separate from the node
		#: tree entirely (see _IGNORED_TEXT_TAGS) so html_to_docx() can parse
		#: an author's :root overrides out of it after the walk finishes.
		self.style_text_parts: list[str] = []
		#: Open inline formatting tags as (tag, href), innermost last.
		self._inline_stack: list[tuple[str, str]] = []
		#: <title> text (the document name), used for the file's core properties.
		self.title = ""
		self._in_title = False

	def _format(self, line_break: bool = False) -> _InlineFormat:
		tags = [tag for tag, _href in self._inline_stack]
		href = next((h for t, h in reversed(self._inline_stack) if t == "a" and h), "")
		return _InlineFormat(
			bold=any(t in ("strong", "b") for t in tags),
			italic=any(t in ("em", "i") for t in tags),
			code="code" in tags,
			href=href,
			line_break=line_break,
		)

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		if tag == "title":
			self._in_title = True
			return
		if tag in _IGNORED_TEXT_TAGS:
			self._ignored_depth += 1
			self._ignored_tag_stack.append(tag)
			return
		if self._ignored_depth:
			return

		attr_dict = {key: (value or "") for key, value in attrs}

		if tag == "hr":
			# hr is a void element: `<hr>` (what python-markdown emits for
			# `---`) has no end tag, so opening it as the current node made
			# EVERY block after a horizontal rule its child - and hr renders
			# none of its children, so the rest of the document vanished
			# from the DOCX. It is a leaf, like img.
			self._current.add_child(_Node(tag, attr_dict, parent=self._current))
			return

		if _opens_node(tag, attr_dict):
			node = _Node(tag, attr_dict, parent=self._current)
			self._current.add_child(node)
			self._current = node
		elif tag == "img":
			# img is a void element (no matching handle_endtag) — record it as
			# a leaf child of the current node so text order is preserved.
			node = _Node(tag, attr_dict, parent=self._current)
			self._current.add_child(node)
		elif tag == "br":
			self._current.add_text("\n", self._format(line_break=True))
		elif tag in _INLINE_FORMAT_TAGS:
			self._inline_stack.append((tag, attr_dict.get("href", "")))
		# Other inline tags (strong, em, a, span, code without a component
		# class) don't need their own node — their text is folded into the
		# enclosing block's text.

	def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		if tag == "img":
			self.handle_starttag(tag, attrs)
		elif tag == "br":
			self.handle_starttag(tag, attrs)
		elif tag == "hr":
			self.handle_starttag(tag, attrs)

	def handle_endtag(self, tag: str) -> None:
		if tag == "title":
			self._in_title = False
			return
		if tag in _IGNORED_TEXT_TAGS:
			self._ignored_depth = max(0, self._ignored_depth - 1)
			if self._ignored_tag_stack:
				self._ignored_tag_stack.pop()
			return
		if self._ignored_depth:
			return

		# self._current.tag can only equal `tag` here if a node was actually
		# opened for it (see _opens_node) — a plain <span> or <strong> never
		# becomes `self._current`, so its close tag is a no-op, same as before.
		if self._current is not self.root and self._current.tag == tag:
			self._current = self._current.parent or self.root
			return
		if tag in _INLINE_FORMAT_TAGS:
			for index in range(len(self._inline_stack) - 1, -1, -1):
				if self._inline_stack[index][0] == tag:
					del self._inline_stack[index]
					break

	def handle_data(self, data: str) -> None:
		if self._in_title:
			self.title += data
			return
		if self._ignored_depth:
			# Still inside script/style - the text must not join the node
			# tree (that's what keeps CSS out of the body), but style text
			# specifically is captured for theme parsing. script text is
			# genuinely dropped; nothing downstream needs it.
			if self._ignored_tag_stack and self._ignored_tag_stack[-1] == "style":
				self.style_text_parts.append(data)
			return
		self._current.add_text(data, self._format())


#: Matches one ``:root { ... }`` block's body. Author CSS may contain more
#: than one :root rule (e.g. a base one plus a media-query-guarded override
#: that still landed unconditionally after sanitization) - finditer() below
#: walks them in source order so a later block's declarations win, matching
#: normal CSS cascade behaviour for repeated declarations of the same
#: property.
_ROOT_BLOCK_RE = re.compile(r":root\s*\{([^}]*)\}", re.DOTALL)

#: Matches one ``--token: value;`` custom-property declaration inside a
#: :root block. Deliberately permissive about the token charset and
#: whitespace/newlines - author CSS is free-form text we don't control.
_CSS_CUSTOM_PROP_RE = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;}]+);?")

#: Matches a bare #RGB or #RRGGBB colour literal, nothing else. Used to
#: reject non-colour custom properties (e.g. ``--gap: 8pt``) before they can
#: reach OOXML, which has no notion of any other CSS value shape.
_HEX_COLOR_RE = re.compile(r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


def _normalize_hex_color(value: str) -> str | None:
	"""Return a ``#RRGGBB`` literal for a ``#RGB``/``#RRGGBB`` value, or
	``None`` if ``value`` isn't a hex colour at all (e.g. ``8pt``, ``red``,
	``rgb(1,2,3)``). OOXML colour attributes require exactly 6 hex digits -
	python-docx's ``RGBColor.from_string`` does not expand the 3-digit CSS
	shorthand, so ``#D33`` reaching python-docx unexpanded raises instead of
	degrading gracefully.
	"""
	match = _HEX_COLOR_RE.match(value.strip())
	if not match:
		return None
	digits = match.group(1)
	if len(digits) == 3:
		digits = "".join(ch * 2 for ch in digits)
	return f"#{digits.upper()}"


def _extract_theme(style_text: str) -> dict:
	"""Parse an author's ``:root { --token: value; }`` overrides out of the
	raw text captured from every <style> tag, and return the effective theme:
	the registry defaults (``components.THEME``) updated with whatever the
	author validly overrode.

	This must never raise - a malformed or hostile <style> block should
	degrade to the default palette, not break the export. Every failure mode
	(no :root block, an unparsable declaration, a non-colour value, an
	unknown token) is handled by simply not updating that entry, rather than
	by catching exceptions from deep inside a parse - the regexes above are
	permissive enough that a try/except around the whole function is only a
	last-resort safety net, not the primary defence.
	"""
	theme = dict(THEME)
	if not style_text:
		return theme

	try:
		for root_match in _ROOT_BLOCK_RE.finditer(style_text):
			block_body = root_match.group(1)
			for decl_match in _CSS_CUSTOM_PROP_RE.finditer(block_body):
				token = decl_match.group(1).strip()
				raw_value = decl_match.group(2).strip()
				normalized = _normalize_hex_color(raw_value)
				if normalized is None:
					# Non-colour custom property (e.g. --gap: 8pt) or a CSS
					# colour keyword/function we don't attempt to resolve -
					# leave whatever this token was already set to (default,
					# or an earlier :root block's value) rather than write a
					# value OOXML can't use.
					continue
				theme[token] = normalized
	except Exception:
		# Never let a theme-parsing surprise take down the whole export -
		# fall back to the registry defaults, exactly as if the document
		# carried no <style> block at all.
		return dict(THEME)

	return theme


def _apply_alignment_and_indent(paragraph, node: _Node) -> None:
	classes = node.classes()

	for class_name, alignment in _ALIGNMENTS.items():
		if class_name in classes:
			paragraph.alignment = alignment
			break

	for class_name, level in _INDENTS.items():
		if class_name in classes:
			paragraph.paragraph_format.left_indent = Inches(0.5 * level)
			break


def _add_heading(container, text: str, level: int):
	"""Add a heading paragraph to ``container``. Used both for plain h1-h6
	tags and the "doc-title" component recipe. ``Document.add_heading``
	isn't available on a table ``_Cell``, so this applies the equivalent
	built-in heading/title style directly via ``add_paragraph`` instead,
	which both ``Document`` and ``_Cell`` support.
	"""
	style = f"Heading {level}" if level else "Title"
	return container.add_paragraph(text, style=style)


def _add_image(container, node: _Node) -> None:
	src = node.attrs.get("src") or ""
	if not src.startswith("data:"):
		# http(s) URLs (or anything else) are skipped — no network calls.
		return

	try:
		header, _, encoded = src.partition(",")
		if ";base64" not in header:
			return
		image_bytes = base64.b64decode(encoded)
		# Document.add_picture() is a convenience method not available on a
		# table _Cell — adding the run explicitly works in either container.
		paragraph = container.add_paragraph()
		_add_picture_run(paragraph, image_bytes)
	except Exception:
		# Best-effort: a malformed data URI should not crash the export.
		pass


def _add_table(container, table_node: _Node, theme: dict):
	"""Build a plain docx table from a sanitized <table> node's rows/cells.

	Returns the created ``Table`` (or ``None`` if the source had no rows) so
	callers - notably the "data-table" component recipe - can post-process
	it (e.g. shade the header row) without re-walking the HTML.
	"""
	rows: list[list[_Node]] = []
	for section in table_node.children:
		if section.tag in ("thead", "tbody"):
			for tr in section.children:
				if tr.tag == "tr":
					rows.append([cell for cell in tr.children if cell.tag in ("th", "td")])
		elif section.tag == "tr":
			rows.append([cell for cell in section.children if cell.tag in ("th", "td")])

	if not rows:
		return None

	num_cols = max(len(row) for row in rows)
	table = container.add_table(rows=len(rows), cols=num_cols)
	table.style = "Table Grid"
	_set_table_widths(table, theme)
	_apply_table_borders(table, theme["rule"])
	_set_table_cell_margins(table)

	for row_index, row in enumerate(rows):
		is_header_row = bool(row) and all(cell.tag == "th" for cell in row)
		for col_index, cell_node in enumerate(row):
			cell = table.cell(row_index, col_index)
			_fill_plain_table_cell(cell, cell_node, theme)
			alignment = _css_text_align(cell_node)
			for paragraph in cell.paragraphs:
				paragraph.paragraph_format.space_after = Pt(0)
				if alignment is not None:
					paragraph.alignment = alignment
			if is_header_row:
				_shade_cell(cell, theme["surface"])
				for paragraph in cell.paragraphs:
					for run in paragraph.runs:
						run.font.bold = True
		if is_header_row:
			_repeat_as_header_row(table.rows[row_index])

	# A table is followed directly by the next block in Word; an empty
	# spacer keeps the HTML's `margin: 1em 0` between a table and whatever
	# comes after it (only at the top level - inside a cell it would add a
	# blank line to a component box).
	if hasattr(container, "add_section"):
		spacer = container.add_paragraph()
		spacer.paragraph_format.space_after = Pt(0)

	return table


def _fill_plain_table_cell(cell, node: _Node, theme: dict) -> None:
	"""Fill one <td>/<th> cell of a plain sanitized <table> (data-table).

	A cell that's just text (``<td><strong>Digital Omnichannel</strong></td>``)
	takes the fast ``cell.text =`` path unchanged from before. A cell that
	contains a component element - the only real case is
	``<td><span class="status-badge ...">In Progress</span></td>`` - used to
	go through the same ``full_text`` path, which drops it: ``span`` is not
	in ``_BLOCK_TAGS``, so a status-badge span's text was never included in
	the td's ``full_text`` even though the span DOES open its own ``_Node``
	(component classes force that - see ``_opens_node``). The badge's text
	vanished from the export entirely, and even where a future component
	happened to still have SOME text reach the cell, it would arrive as bare
	text with the recipe's styling (shading/bold/etc.) never applied, since
	nothing here ever called `_render_node` for cell content. Routing
	children through `_render_node` when there are any is what lets a
	table-cell badge actually dispatch to its "run" recipe.
	"""
	if not node.children or all(_is_inline_child(child) for child in node.children):
		# Text (with bold/italic/code/links, and inline badges) written as
		# real runs into the cell's own first paragraph.
		_write_inline(cell.paragraphs[0], node, theme)
		return
	_clear_cell(cell)
	for child in node.children:
		_render_node(cell, child, theme)


def _add_list(container, list_node: _Node, theme: dict, level: int = 0) -> None:
	"""A real Word list: every item is a paragraph bound to a numbering
	definition (numPr), so Word, Pages and Google Docs show real bullets and
	auto-numbers, keep the hanging indent, and nested lists become deeper
	levels instead of being glued into their parent item's text.

	Each ``<ol>`` gets its own numbering instance so it restarts at 1;
	bullets share one instance.
	"""
	ordered = list_node.tag == "ol"
	num_id = _new_list_num(container, theme, ordered)
	for item in list_node.children:
		if item.tag != "li":
			continue
		paragraph = container.add_paragraph()
		_set_numbering(paragraph, num_id, min(level, 8))
		paragraph.paragraph_format.space_after = Pt(2)
		_write_inline(paragraph, item, theme)
		for child in item.children:
			if child.tag in ("ul", "ol"):
				_add_list(container, child, theme, level + 1)


def _render_node(container, node: _Node, theme: dict) -> None:
	class_name, recipe = _component_recipe(node)
	if recipe is not None:
		_render_component(container, node, class_name, recipe, theme)
		return

	tag = node.tag

	if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
		level = int(tag[1])
		paragraph = _add_heading(container, "", level)
		_write_inline(paragraph, node, theme)
		# Plain (non-component) heading tags used to land in Word's built-in
		# Heading-style blue exactly like doc-title before the fix in
		# _render_heading_recipe - observed in production for ordinary
		# <h2>/<h3> tags authored inside a .split (e.g. "Core Strategic
		# Pillars", "Key Snapshot"), which never carry a registry component
		# class at all. The PDF's base stylesheet sets no heading colour, so
		# headings there simply inherit the body's --ink colour; applying
		# theme["ink"] here matches that instead of Word's template default.
		_color_heading_runs(paragraph, theme["ink"])
	elif tag == "p":
		if node.children and all(child.tag == "img" for child in node.children) and not node.full_text:
			for child in node.children:
				_add_image(container, child)
			return
		paragraph = container.add_paragraph()
		_write_inline(paragraph, node, theme)
		_apply_alignment_and_indent(paragraph, node)
	elif tag == "blockquote":
		paragraph = container.add_paragraph()
		_style_quote(paragraph, theme)
		_write_inline(paragraph, node, theme)
		_finish_quote(paragraph, theme)
		_apply_alignment_and_indent(paragraph, node)
	elif tag in ("ul", "ol"):
		_add_list(container, node, theme)
	elif tag == "table":
		_add_table(container, node, theme)
	elif tag == "pre":
		_add_code_block(container, node, theme)
	elif tag == "hr":
		_add_rule(container, theme)
	elif tag == "img":
		_add_image(container, node)
	elif tag == "div":
		_render_div(container, node, theme)
	elif node.children:
		# Unclassed/unknown container tag - degrade gracefully by rendering
		# children in document order rather than dropping them.
		for child in node.children:
			_render_node(container, child, theme)
	# thead/tbody/tr/th/td/li are handled by their container (table/ul/ol)
	# and should never appear as direct children of the root.


_COLUMNS_CLASS_RE = re.compile(r"^columns-([23])$")


def _render_div(container, node: _Node, theme: dict) -> None:
	"""Render a <div> that is not carrying a registry component class —
	currently either a ``columns-N`` section wrapper, or an unclassed
	passthrough container. A div without a recognised columns class renders
	as a plain passthrough (its children rendered inline, no section
	change), so future non-columns div usage degrades gracefully rather than
	silently dropping content.
	"""
	column_count = None
	for class_name in node.classes():
		match = _COLUMNS_CLASS_RE.match(class_name)
		if match:
			column_count = int(match.group(1))
			break

	# Columns require a real docx section, which only exists at the
	# Document level - a div nested inside a table cell (e.g. inside a
	# callout) can't open one, so it degrades to a plain passthrough too.
	if column_count is None or not hasattr(container, "add_section"):
		for child in node.children:
			_render_node(container, child, theme)
		return

	_set_section_columns(container.add_section(WD_SECTION.CONTINUOUS), column_count)
	for child in node.children:
		_render_node(container, child, theme)
	# Close the columns region: a fresh CONTINUOUS section reset to a single
	# column, so content after the div returns to normal single-column flow
	# rather than inheriting the multi-column layout indefinitely.
	_set_section_columns(container.add_section(WD_SECTION.CONTINUOUS), 1)


def _set_section_columns(section, column_count: int) -> None:
	"""Set the number of layout columns on a docx section via its raw
	sectPr XML — python-docx has no public column-count API. A freshly
	created section's sectPr has no <w:cols> element yet, so one is created
	if absent rather than assumed to already exist.
	"""
	sect_pr = section._sectPr
	cols = sect_pr.find(qn("w:cols"))
	if cols is None:
		cols = OxmlElement("w:cols")
		sect_pr.append(cols)
	cols.set(qn("w:num"), str(column_count))


# ---------------------------------------------------------------------------
# Component dispatch
#
# The functions below interpret a component's "docx" recipe (read from
# COMPONENTS at call time - never copied/hardcoded here) against the node it
# was found on. Each one accepts the same `container` (Document or _Cell)
# that ordinary node rendering uses, so nested content - a callout's
# children, a split cell's paragraphs, a metric's value/label - keeps
# flowing through the same _render_node() machinery as everything else.
# ---------------------------------------------------------------------------


def _component_recipe(node: _Node):
	"""Return (class_name, docx recipe dict) for the first registry class
	found on `node`, or (None, None) if it carries none. Iterates
	COMPONENTS (dict order) rather than the node's own (unordered) class set
	so dispatch is deterministic if an element ever carried more than one
	registry class.
	"""
	classes = node.classes()
	for class_name in COMPONENTS:
		if class_name in classes:
			return class_name, COMPONENTS[class_name]["docx"]
	return None, None


def _render_component(container, node: _Node, class_name: str, recipe: dict, theme: dict) -> None:
	kind = recipe.get("type")
	if kind == "table":
		_render_table_recipe(container, node, recipe, theme)
	elif kind == "table_row_of_cells":
		_render_metric_grid(container, node, recipe, theme)
	elif kind == "cell":
		_render_cell_recipe(container, node, recipe, theme)
	elif kind == "run":
		_render_run_recipe(container, node, recipe, theme)
	elif kind == "paragraph":
		_render_paragraph_recipe(container, node, recipe, theme)
	elif kind == "heading":
		_render_heading_recipe(container, node, recipe, theme)
	elif kind == "passthrough":
		_render_passthrough_recipe(container, node, theme)
	elif kind == "page_break":
		_render_page_break_recipe(container, node, recipe)
	elif kind == "footer":
		_render_footer_recipe(container, node, recipe, theme)
	else:
		# Unknown recipe type: degrade gracefully rather than drop content.
		for child in node.children:
			_render_node(container, child, theme)


def _render_table_recipe(container, node: _Node, recipe: dict, theme: dict) -> None:
	"""type: "table". Two shapes, distinguished by the recipe itself:

	- Has "cols": the class is on an arbitrary container (div) whose direct
	  children become the table's cells (doc-header, callout, split).
	- No "cols": the class is on a real sanitized <table> (data-table) - the
	  existing row/cell walker builds the table, this only adds header
	  shading on top.
	"""
	if "cols" in recipe:
		_render_synthetic_table(container, node, recipe, theme)
	else:
		_render_data_table(container, node, recipe, theme)


def _render_data_table(container, node: _Node, recipe: dict, theme: dict) -> None:
	table = _add_table(container, node, theme)
	if table is None or not table.rows:
		return

	header_shading = resolve_theme_token(recipe.get("header_shading"), theme) if recipe.get("header_shading") else None
	header_color = resolve_theme_token(recipe.get("header_color"), theme) if recipe.get("header_color") else None
	for cell in table.rows[0].cells:
		if header_shading:
			_shade_cell(cell, header_shading)
		if header_color:
			for paragraph in cell.paragraphs:
				for run in paragraph.runs:
					run.font.color.rgb = _rgb_color(header_color)
					run.font.bold = True


def _render_synthetic_table(container, node: _Node, recipe: dict, theme: dict) -> None:
	cols = recipe["cols"]

	# Assign each direct child its own cell in document order; if there are
	# more children than columns (or exactly one column, e.g. callout), the
	# overflow lands in the last cell together rather than being dropped.
	cell_children: list[list[_Node]] = [[] for _ in range(cols)]
	for index, child in enumerate(node.children):
		cell_children[min(index, cols - 1)].append(child)

	table = container.add_table(rows=1, cols=cols)
	_set_table_borders(table, recipe.get("borders", True), theme["rule"])
	_set_table_widths(table, theme, recipe.get("widths"))

	shading = recipe.get("shading")
	col_align = recipe.get("col_align")

	for col_index in range(cols):
		cell = table.cell(0, col_index)
		if shading and cols == 1:
			_shade_cell(cell, resolve_theme_token(shading, theme))

		contents = cell_children[col_index]
		if contents:
			_clear_cell(cell)
			for child in contents:
				_render_node(cell, child, theme)
		elif cols == 1 and node.text:
			# A node like <div class="callout"><strong>X:</strong> tail
			# text</div> has no child _Node at all (see _opens_node - a
			# bare <strong> without a component class never opens one), so
			# ALL of its text - "X: tail text" - sits on the *node's own*
			# text_parts, and `contents` above is empty. Observed in
			# production: an executive-summary callout authored exactly
			# this way exported with a visually correct box and NO text in
			# it. Gated to cols == 1 (callout is the only single-column
			# user of this recipe shape): for a multi-column recipe
			# (doc-header, split) the parent node's text can't be
			# attributed to one particular empty column, so this fallback
			# would duplicate it into every empty column instead of fixing
			# anything. _render_cell_recipe has the equivalent fallback for
			# the split/metric "cell" recipe shape; this mirrors it for the
			# "table" shape.
			_write_inline(cell.paragraphs[0], node, theme)

		if col_align and col_index < len(col_align):
			alignment = _ALIGNMENTS.get(f"text-{col_align[col_index]}")
			if alignment is not None:
				for paragraph in cell.paragraphs:
					paragraph.alignment = alignment


def _render_metric_grid(container, node: _Node, recipe: dict, theme: dict) -> None:
	"""type: "table_row_of_cells" (metric-grid). One table, 2 columns per
	row, so 4 .metric children become a 2x2 table - matching how the PDF
	lays them out via CSS grid. Each metric child is rendered through the
	normal component dispatch (its own "metric" recipe fills the cell we
	hand it), so this function only owns the row/column bookkeeping.
	"""
	metrics = node.children
	if not metrics:
		return

	cols = 2
	rows = (len(metrics) + cols - 1) // cols
	table = container.add_table(rows=rows, cols=cols)
	_set_table_widths(table, theme)

	for index, metric_node in enumerate(metrics):
		row_index, col_index = divmod(index, cols)
		cell = table.cell(row_index, col_index)
		# Cell clearing is owned by whichever component recipe fills the
		# cell (see _render_cell_recipe/_render_metric_value_cell) - not
		# done here too, since _clear_cell is only safe to call once on a
		# cell that still has its default empty paragraph.
		_render_node(cell, metric_node, theme)


def _render_cell_recipe(container, node: _Node, recipe: dict, theme: dict) -> None:
	"""type: "cell". Fills `container` (an already-created table cell) with
	this node's content - it does NOT create a new cell itself, since the
	caller (a "table"/"table_row_of_cells" recipe) already built the
	physical cell and handed it in as `container`.

	Two shapes, distinguished by the recipe's own keys: a plain cell
	(split-main/split-side - optional shading, children render normally) or
	a metric cell (has "value_size_pt" - node.text becomes a large bold
	value run, node.attrs[label_from] becomes a small label paragraph).
	"""
	if "value_size_pt" in recipe:
		_render_metric_value_cell(container, node, recipe, theme)
		return

	shading = recipe.get("shading")
	if shading:
		_shade_cell(container, resolve_theme_token(shading, theme))

	if node.children:
		_clear_cell(container)
		for child in node.children:
			_render_node(container, child, theme)
	elif node.text:
		_clear_cell(container)
		container.add_paragraph(node.text)


def _render_metric_value_cell(container, node: _Node, recipe: dict, theme: dict) -> None:
	shading = recipe.get("shading")
	if shading:
		_shade_cell(container, resolve_theme_token(shading, theme))

	_clear_cell(container)

	# node.text (not _all_descendant_text) would only see text sitting
	# DIRECTLY on the .metric node - an author who wraps the value in its
	# own <div class="metric-value"> (matching the CSS, which styles
	# .metric-value separately from .metric) puts that text on a CHILD
	# node instead. node.full_text doesn't help either: div is a
	# _CONTAINER_TAG, so full_text's block-descendant walk skips it on
	# purpose. Observed in production: the metric card rendered with its
	# label but a blank value. _all_descendant_text has no such exclusion.
	value_text = _all_descendant_text(node)
	value_paragraph = container.add_paragraph()
	value_run = value_paragraph.add_run(value_text)
	value_run.font.bold = True
	value_run.font.size = Pt(recipe["value_size_pt"])
	value_color = recipe.get("value_color")
	if value_color:
		value_run.font.color.rgb = _rgb_color(resolve_theme_token(value_color, theme))

	label_attr = recipe.get("label_from")
	label_text = node.attrs.get(label_attr, "") if label_attr else ""
	if label_text:
		label_paragraph = container.add_paragraph()
		label_run = label_paragraph.add_run(label_text)
		label_run.font.size = Pt(recipe["label_size_pt"])
		label_color = recipe.get("label_color")
		if label_color:
			label_run.font.color.rgb = _rgb_color(resolve_theme_token(label_color, theme))


def _render_passthrough_recipe(container, node: _Node, theme: dict) -> None:
	"""type: "passthrough" (split, split-main). Renders the node's children
	directly into `container`, in document order, adding NO table/cell/
	wrapper of its own - this is what linearises a .split (a CSS grid in the
	PDF - see components.py's "split" comment) into a single flowing column
	in Word: main content followed by the sidebar block, one after another,
	instead of a two-column table that let a nested data-table overflow its
	cell and get clipped.

	Walks `_ordered_parts` (the same ordering machinery `_all_descendant_text`
	uses) rather than `node.children` alone, so text sitting directly on the
	node itself - not inside a child element, e.g.
	``<div class="split">intro text<div class="split-side">...</div></div>``
	- is rendered as its own paragraph in the right position instead of
	silently disappearing (a bare _Node.children walk would only see the
	``split-side`` child and drop "intro text" entirely).
	"""
	for kind, value, _fmt in node._ordered_parts:
		if kind == "text":
			text = value.strip()
			if text:
				container.add_paragraph(text)
		else:
			_render_node(container, value, theme)


def _render_run_recipe(container, node: _Node, recipe: dict, theme: dict) -> None:
	"""type: "run" (brand, status-badge). A single run in its own paragraph,
	optionally bold/coloured/shaded/sized.
	"""
	paragraph = container.add_paragraph()
	run = paragraph.add_run(node.text)
	if recipe.get("bold"):
		run.font.bold = True
	color = recipe.get("color")
	if color:
		run.font.color.rgb = _rgb_color(resolve_theme_token(color, theme))
	size_pt = recipe.get("size_pt")
	if size_pt:
		run.font.size = Pt(size_pt)
	shading = recipe.get("shading")
	if shading:
		_shade_run(run, resolve_theme_token(shading, theme))


def _render_paragraph_recipe(container, node: _Node, recipe: dict, theme: dict) -> None:
	"""type: "paragraph" (doc-meta, doc-subtitle)."""
	paragraph = container.add_paragraph(node.full_text)

	align = recipe.get("align")
	alignment = _ALIGNMENTS.get(f"text-{align}") if align else None
	if alignment is not None:
		paragraph.alignment = alignment

	size_pt = recipe.get("size_pt")
	color = recipe.get("color")
	if paragraph.runs and (size_pt or color):
		run = paragraph.runs[0]
		if size_pt:
			run.font.size = Pt(size_pt)
		if color:
			run.font.color.rgb = _rgb_color(resolve_theme_token(color, theme))


def _render_heading_recipe(container, node: _Node, recipe: dict, theme: dict) -> None:
	"""type: "heading" (doc-title). Word's built-in Heading/Title styles
	carry their OWN colour (a blue that belongs to the default template, not
	to this document) - see components.py's "doc-title" comment: a themed
	document's brand line took the theme colour while its title stayed
	stubbornly Word-blue. An optional "color" key, resolved through
	resolve_theme_token exactly like every other recipe colour, is applied
	to the run(s) here instead of being left to the built-in style.
	"""
	paragraph = _add_heading(container, node.full_text, recipe.get("level", 1))
	color = recipe.get("color")
	if color:
		_color_heading_runs(paragraph, resolve_theme_token(color, theme))


def _color_heading_runs(paragraph, hex_color: str) -> None:
	"""Set an explicit colour on every run of a heading paragraph, so it
	overrides whichever built-in Heading/Title style Word would otherwise
	paint blue. `add_paragraph(text, style=...)` puts the whole string into
	a single run today, but this loops rather than assuming exactly one run
	exists, in case a future heading ever carries mixed-run content.
	"""
	for run in paragraph.runs:
		run.font.color.rgb = _rgb_color(hex_color)


def _render_page_break_recipe(container, node: _Node, recipe: dict) -> None:
	"""type: "page_break" (page-break). A real Word page break, not a
	visible rule - see components.py's "page-break" comment: an
	agent-authored dashed-rule version of this got WeasyPrint to paint a
	stray line above every forced break. This only forces the break.

	``add_break(WD_BREAK.PAGE)`` requires an existing run to carry the
	break character, and is not available on a bare paragraph - a fresh run
	on a fresh paragraph is the standard python-docx idiom for an
	unaccompanied page break.
	"""
	paragraph = container.add_paragraph()
	paragraph.add_run().add_break(WD_BREAK.PAGE)


def _render_footer_recipe(container, node: _Node, recipe: dict, theme: dict) -> None:
	"""type: "footer" (doc-footer). Writes into the document's real Word
	section footer, so the text repeats on every page - see components.py's
	"doc-footer" comment: a plain body paragraph only ever appeared once,
	mid-flow, defeating the point of a running footer.

	Only meaningful at the Document level: `container` here is always
	`doc` in practice (doc-footer is never nested inside another
	component's cell in the sanitized vocabulary), but this checks for
	`sections` defensively rather than assuming it, since a table _Cell has
	no notion of a footer to write into.
	"""
	if not hasattr(container, "sections"):
		# No Document reachable from here (e.g. doc-footer nested inside a
		# table cell) - degrade to an ordinary paragraph in place rather
		# than silently dropping the footer text.
		container.add_paragraph(node.full_text)
		return

	footer = container.sections[0].footer
	footer.is_linked_to_previous = False
	paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
	paragraph.text = ""
	run = paragraph.add_run(node.full_text)

	size_pt = recipe.get("size_pt")
	if size_pt:
		run.font.size = Pt(size_pt)
	color = recipe.get("color")
	if color:
		run.font.color.rgb = _rgb_color(resolve_theme_token(color, theme))

	_add_page_number_field(paragraph)


def _add_page_number_field(paragraph) -> None:
	"""Append " | Page {PAGE} of {NUMPAGES}" to a footer paragraph as real
	Word fields, not literal text - the whole reason doc-footer moved out of
	the body (see components.py's "doc-footer" comment) was so authors never
	again hand-write a page count that's wrong the moment pagination
	changes.

	python-docx has no field API, so this is raw OOXML: a field is a
	begin/instrText/separate/end fldChar sequence split across runs, per the
	OOXML spec (ECMA-376 17.16.18) - there is no simpler supported shape.
	"""
	paragraph.add_run("   |   Page ")
	_add_field_run(paragraph, "PAGE")
	paragraph.add_run(" of ")
	_add_field_run(paragraph, "NUMPAGES")


def _add_field_run(paragraph, field_code: str) -> None:
	"""A complex field in Word's own shape: begin / instruction / separate /
	cached result / end, each in its own run. The cached result ("1") is a
	separate plain run so renderers that do not evaluate fields
	(docx-preview drops every run holding a fldChar or instrText) still show
	a number; Word, Pages and Google Docs recompute it on open."""

	def field_char(kind: str) -> None:
		element = OxmlElement("w:fldChar")
		element.set(qn("w:fldCharType"), kind)
		paragraph.add_run()._r.append(element)

	field_char("begin")
	instr_text = OxmlElement("w:instrText")
	instr_text.set(qn("xml:space"), "preserve")
	instr_text.text = f" {field_code} "
	paragraph.add_run()._r.append(instr_text)
	field_char("separate")
	paragraph.add_run("1")
	field_char("end")


# ---------------------------------------------------------------------------
# Document look: page, styles, inline runs, lists, code, rules, footer.
#
# The target is that the .docx a person downloads looks like the Document
# view (render_document_html) in Word, Pages, Google Docs AND in the app's
# own byte-level preview (docx-preview). Every visual property is therefore
# written as explicit OOXML rather than left to the python-docx template's
# theme: theme fonts, style-only table borders and the Symbol-font bullet
# glyph all rendered differently (or not at all) outside Word - see
# evidence/docx-fidelity.md.
# ---------------------------------------------------------------------------

#: Fonts present on Windows, macOS and Google Docs, so every renderer draws
#: the same face. Families, sizes and spacing come from design_tokens, the
#: same module the HTML/PDF stylesheet reads, so the formats cannot drift.
BODY_FONT = tokens.BODY_FONT
HEADING_FONT = tokens.HEADING_FONT
MONO_FONT = tokens.MONO_FONT

#: Heading sizes and spacing mirror PRINT_STYLESHEET's h1-h6 rules.
_HEADING_SIZES_PT = tokens.HEADING_SIZES_PT
_HEADING_SPACE_BEFORE_PT = tokens.HEADING_SPACE_BEFORE_PT

#: OOXML child order for the property elements this module inserts into, so
#: every element lands where the schema (and strict consumers) expect it.
_P_PR_ORDER = (
	"w:pStyle", "w:keepNext", "w:keepLines", "w:pageBreakBefore", "w:framePr", "w:widowControl",
	"w:numPr", "w:suppressLineNumbers", "w:pBdr", "w:shd", "w:tabs", "w:suppressAutoHyphens",
	"w:kinsoku", "w:wordWrap", "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN",
	"w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing",
	"w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment",
	"w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
)
_R_PR_ORDER = (
	"w:rStyle", "w:rFonts", "w:b", "w:bCs", "w:i", "w:iCs", "w:caps", "w:smallCaps", "w:strike",
	"w:dstrike", "w:outline", "w:shadow", "w:emboss", "w:imprint", "w:noProof", "w:snapToGrid",
	"w:vanish", "w:webHidden", "w:color", "w:spacing", "w:w", "w:kern", "w:position", "w:sz",
	"w:szCs", "w:highlight", "w:u", "w:effect", "w:bdr", "w:shd", "w:fitText", "w:vertAlign",
	"w:rtl", "w:cs", "w:em", "w:lang", "w:eastAsianLayout", "w:specVanish", "w:oMath",
)
_TBL_PR_ORDER = (
	"w:tblStyle", "w:tblpPr", "w:tblOverlap", "w:bidiVisual", "w:tblStyleRowBandSize",
	"w:tblStyleColBandSize", "w:tblW", "w:jc", "w:tblCellSpacing", "w:tblInd", "w:tblBorders",
	"w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook", "w:tblCaption", "w:tblDescription",
)
_TC_PR_ORDER = (
	"w:cnfStyle", "w:tcW", "w:gridSpan", "w:hMerge", "w:vMerge", "w:tcBorders", "w:shd",
	"w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark",
)
_TR_PR_ORDER = (
	"w:cnfStyle", "w:divId", "w:gridBefore", "w:gridAfter", "w:wBefore", "w:wAfter", "w:cantSplit",
	"w:trHeight", "w:tblHeader", "w:tblCellSpacing", "w:jc", "w:hidden",
)

#: Bullet glyphs per level, drawn in the body font (the template's Symbol
#: font bullet showed as an empty box in docx-preview).
_BULLET_GLYPHS = ("•", "◦", "▪")
_ORDERED_FORMATS = (("decimal", "%{n}."), ("lowerLetter", "%{n}."), ("lowerRoman", "%{n}."))

_TEXT_ALIGN_RE = re.compile(r"text-align\s*:\s*(left|center|right)", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def _insert_ordered(parent, element, order: tuple) -> None:
	"""Insert ``element`` into ``parent`` before the first existing child that
	must follow it in schema order, replacing any existing element of the
	same tag."""
	tag = element.tag
	for existing in parent.findall(tag):
		parent.remove(existing)
	name = next((n for n in order if qn(n) == tag), None)
	successors = order[order.index(name) + 1 :] if name else ()
	parent.insert_element_before(element, *successors)


def _set_rfonts(r_pr, font: str) -> None:
	"""Explicit fonts on an rPr, dropping theme-font attributes (which take
	precedence over ascii/hAnsi and resolve to the template theme)."""
	fonts = OxmlElement("w:rFonts")
	for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
		fonts.set(qn(attr), font)
	_insert_ordered(r_pr, fonts, _R_PR_ORDER)


def _border_el(tag: str, color: str, size: int = 4, space: int = 0, val: str = "single"):
	el = OxmlElement(tag)
	el.set(qn("w:val"), val)
	el.set(qn("w:sz"), str(size))
	el.set(qn("w:space"), str(space))
	el.set(qn("w:color"), _docx_hex(color))
	return el


def _paragraph_borders(p_pr, color: str, edges: dict) -> None:
	"""edges: {"left": (size_eighths, space_pt), ...}"""
	border = OxmlElement("w:pBdr")
	for edge in ("top", "left", "bottom", "right"):
		if edge in edges:
			size, space = edges[edge]
			border.append(_border_el(f"w:{edge}", color, size, space))
	_insert_ordered(p_pr, border, _P_PR_ORDER)


def _paragraph_shading(p_pr, color: str) -> None:
	shd = OxmlElement("w:shd")
	shd.set(qn("w:val"), "clear")
	shd.set(qn("w:color"), "auto")
	shd.set(qn("w:fill"), _docx_hex(color))
	_insert_ordered(p_pr, shd, _P_PR_ORDER)


def _setup_document(doc, theme: dict, title: str) -> None:
	"""Page geometry and styles matching PRINT_STYLESHEET: A4, 2cm margins,
	body size from design_tokens, one sans face for title and headings in the ink colour, no Word-blue anywhere."""
	section = doc.sections[0]
	section.page_width = Cm(21)
	section.page_height = Cm(29.7)
	for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
		setattr(section, side, Cm(2))
	section.header_distance = Cm(1)
	section.footer_distance = Cm(1)

	styles = doc.styles
	# docDefaults carry theme fonts; replace them so any style that does not
	# name a font still resolves to the body font.
	defaults = styles.element.find(qn("w:docDefaults"))
	if defaults is not None:
		r_pr_default = defaults.find(qn("w:rPrDefault"))
		if r_pr_default is not None and r_pr_default.find(qn("w:rPr")) is not None:
			_set_rfonts(r_pr_default.find(qn("w:rPr")), BODY_FONT)

	normal = styles["Normal"]
	_set_rfonts(normal.element.get_or_add_rPr(), BODY_FONT)
	normal.font.size = Pt(tokens.BODY_SIZE_PT)
	normal.font.color.rgb = _rgb_color(theme["ink"])
	normal.paragraph_format.space_after = Pt(tokens.PARA_SPACE_AFTER_PT)
	normal.paragraph_format.line_spacing = tokens.DOCX_BODY_LINE_SPACING

	for style_name, level in [("Title", 1)] + [(f"Heading {n}", n) for n in range(1, 7)]:
		try:
			style = styles[style_name]
		except KeyError:
			continue
		# One sans face at every level, as in PRINT_STYLESHEET.
		level_font = HEADING_FONT
		_set_rfonts(style.element.get_or_add_rPr(), level_font)
		style.font.size = Pt(_HEADING_SIZES_PT[level])
		style.font.bold = True
		style.font.italic = False
		style.font.color.rgb = _rgb_color(theme["ink"])
		fmt = style.paragraph_format
		fmt.space_before = Pt(_HEADING_SPACE_BEFORE_PT[level])
		fmt.space_after = Pt(tokens.HEADING_SPACE_AFTER_PT[level])
		fmt.keep_with_next = True
		fmt.line_spacing = tokens.DOCX_HEADING_LINE_SPACING
		# The linked character style ("Heading 1 Char") carries its own
		# template font/size/colour, and docx-preview merges it into the
		# paragraph - so it must match too.
		try:
			char_style = styles[f"{style_name} Char"]
		except KeyError:
			char_style = None
		if char_style is not None:
			_set_rfonts(char_style.element.get_or_add_rPr(), level_font)
			char_style.font.size = Pt(_HEADING_SIZES_PT[level])
			char_style.font.bold = True
			char_style.font.italic = False
			char_style.font.color.rgb = _rgb_color(theme["ink"])
		# The template's Title style draws a blue bottom border.
		p_pr = style.element.get_or_add_pPr()
		for border in p_pr.findall(qn("w:pBdr")):
			p_pr.remove(border)

	props = doc.core_properties
	props.title = title or ""
	props.author = ""
	props.last_modified_by = ""
	props.comments = ""
	props.revision = 1


def _css_text_align(node: _Node):
	"""Alignment from an inline ``style="text-align: right"`` (python-markdown's
	tables extension writes column alignment this way) or an align class."""
	match = _TEXT_ALIGN_RE.search(node.attrs.get("style") or "")
	if match:
		return _ALIGNMENTS.get(f"text-{match.group(1).lower()}")
	for class_name, alignment in _ALIGNMENTS.items():
		if class_name in node.classes():
			return alignment
	return None


def _is_inline_child(node: _Node) -> bool:
	"""Children that belong inside a paragraph's run flow: images and inline
	component spans (status-badge, brand) - not blocks."""
	if node.tag == "img":
		return True
	_name, recipe = _component_recipe(node)
	return bool(recipe) and recipe.get("type") == "run" and node.tag not in _BLOCK_TAGS


def _collect_inline(node: _Node, segments: list, *, preserve_whitespace: bool = False) -> None:
	"""Flatten ``node`` into ("text", str, fmt) / ("break",) / ("image", node) /
	("badge", node, recipe) segments in document order. Nested lists are
	skipped (the list renderer places them as deeper levels); nested block
	children (a loose list item's <p>, a blockquote's <p>s) are joined with a
	line break, the same thing the HTML shows."""
	for kind, value, fmt in node._ordered_parts:
		if kind == "text":
			if fmt is not None and fmt.line_break:
				segments.append(("break",))
			else:
				segments.append(("text", value, fmt or _PLAIN))
			continue
		child = value
		if child.tag in ("ul", "ol"):
			continue
		if child.tag == "img":
			segments.append(("image", child))
			continue
		_name, recipe = _component_recipe(child)
		if recipe and recipe.get("type") == "run":
			segments.append(("badge", child, recipe))
			continue
		if child.tag in _BLOCK_TAGS:
			if any(seg[0] != "break" and (seg[0] != "text" or seg[1].strip()) for seg in segments):
				segments.append(("break",))
			_collect_inline(child, segments, preserve_whitespace=preserve_whitespace)
			continue
		segments.append(("text", _all_descendant_text(child), _PLAIN))


def _normalize_inline(segments: list) -> list:
	"""HTML whitespace rules: collapse runs of whitespace to one space, drop
	leading whitespace at the start of a line and trailing whitespace before
	a break or the end."""
	out = []
	at_line_start = True
	for seg in segments:
		if seg[0] == "text":
			text = _WHITESPACE_RE.sub(" ", seg[1])
			if at_line_start or (out and out[-1][0] == "text" and out[-1][1].endswith(" ")):
				text = text.lstrip(" ")
			if not text:
				continue
			out.append(("text", text, seg[2]))
			at_line_start = False
		elif seg[0] == "break":
			_rstrip_last(out)
			out.append(seg)
			at_line_start = True
		else:
			out.append(seg)
			at_line_start = False
	_rstrip_last(out)
	while out and out[-1][0] == "break":
		out.pop()
	return out


def _rstrip_last(out: list) -> None:
	if out and out[-1][0] == "text":
		stripped = out[-1][1].rstrip(" ")
		if stripped:
			out[-1] = ("text", stripped, out[-1][2])
		else:
			out.pop()


def _write_inline(paragraph, node: _Node, theme: dict) -> None:
	"""Write ``node``'s inline content into ``paragraph`` as formatted runs."""
	segments: list = []
	_collect_inline(node, segments)
	for seg in _normalize_inline(segments):
		if seg[0] == "text":
			_add_text_run(paragraph, seg[1], seg[2], theme)
		elif seg[0] == "break":
			paragraph.add_run().add_break()
		elif seg[0] == "image":
			image_bytes = _data_uri_bytes(seg[1].attrs.get("src") or "")
			if image_bytes:
				try:
					_add_picture_run(paragraph, image_bytes)
				except Exception:  # noqa: BLE001, S110 - a bad image must not fail the export
					pass
		elif seg[0] == "badge":
			_add_badge_run(paragraph, seg[1], seg[2], theme)


def _add_text_run(paragraph, text: str, fmt: _InlineFormat, theme: dict):
	if fmt.href and _is_safe_href(fmt.href):
		return _add_hyperlink_run(paragraph, text, fmt, theme)
	run = paragraph.add_run(text)
	_format_run(run, fmt, theme)
	return run


def _format_run(run, fmt: _InlineFormat, theme: dict) -> None:
	if fmt.bold:
		run.font.bold = True
	if fmt.italic:
		run.font.italic = True
	if fmt.code:
		r_pr = run._r.get_or_add_rPr()
		_set_rfonts(r_pr, MONO_FONT)
		run.font.size = Pt(tokens.CODE_SIZE_PT)
		_shade_run(run, theme["surface"])


def _is_safe_href(href: str) -> bool:
	return href.lower().startswith(("http://", "https://", "mailto:"))


def _add_hyperlink_run(paragraph, text: str, fmt: _InlineFormat, theme: dict):
	"""A real, clickable w:hyperlink (external relationship), styled like
	the HTML's link: accent colour, underlined."""
	from docx.opc.constants import RELATIONSHIP_TYPE as RT
	from docx.text.run import Run

	r_id = paragraph.part.relate_to(fmt.href, RT.HYPERLINK, is_external=True)
	hyperlink = OxmlElement("w:hyperlink")
	hyperlink.set(qn("r:id"), r_id)
	r = OxmlElement("w:r")
	hyperlink.append(r)
	paragraph._p.append(hyperlink)
	run = Run(r, paragraph)
	run.text = text
	_format_run(run, fmt, theme)
	run.font.color.rgb = _rgb_color(theme["accent"])
	run.font.underline = True
	return run


def _add_badge_run(paragraph, node: _Node, recipe: dict, theme: dict) -> None:
	"""A "run" component (status-badge, brand) inline in running text."""
	run = paragraph.add_run(_all_descendant_text(node))
	if recipe.get("bold"):
		run.font.bold = True
	color = recipe.get("color")
	if color:
		run.font.color.rgb = _rgb_color(resolve_theme_token(color, theme))
	size_pt = recipe.get("size_pt")
	if size_pt:
		run.font.size = Pt(size_pt)
	shading = recipe.get("shading")
	if shading:
		_shade_run(run, resolve_theme_token(shading, theme))


def _data_uri_bytes(src: str) -> bytes | None:
	if not src.startswith("data:"):
		return None
	header, _, encoded = src.partition(",")
	if ";base64" not in header:
		return None
	try:
		return base64.b64decode(encoded)
	except ValueError:
		return None


def _add_picture_run(paragraph, image_bytes: bytes) -> None:
	"""Add an inline picture no wider than the page's content area."""
	run = paragraph.add_run()
	shape = run.add_picture(io.BytesIO(image_bytes))
	max_width = _content_width_of(paragraph)
	if shape.width and shape.width > max_width:
		shape.height = int(shape.height * max_width / shape.width)
		shape.width = max_width


def _content_width_of(paragraph) -> int:
	try:
		return _document_content_width_emu(paragraph.part.document)
	except (AttributeError, IndexError):
		return _FALLBACK_CONTENT_WIDTH_EMU


def _style_quote(paragraph, theme: dict) -> None:
	"""blockquote: a left rule in --rule, muted italic text, like the HTML."""
	p_pr = paragraph._p.get_or_add_pPr()
	_paragraph_borders(p_pr, theme["rule"], {"left": (24, 8)})
	paragraph.paragraph_format.left_indent = Pt(12)
	paragraph.paragraph_format.space_before = Pt(6)
	paragraph.paragraph_format.space_after = Pt(10)


def _finish_quote(paragraph, theme: dict) -> None:
	"""Quote text is muted italic unless a run already set its own."""
	for run in paragraph.runs:
		if run.font.italic is None:
			run.font.italic = True
		if run.font.color.rgb is None:
			run.font.color.rgb = _rgb_color(theme["muted"])


def _add_code_block(container, node: _Node, theme: dict) -> None:
	"""pre: one shaded, bordered paragraph in the mono font; the source's
	line breaks and indentation are kept exactly."""
	text = _all_descendant_text_raw(node).strip("\n")
	paragraph = container.add_paragraph()
	p_pr = paragraph._p.get_or_add_pPr()
	_paragraph_borders(p_pr, theme["rule"], {edge: (4, 6) for edge in ("top", "left", "bottom", "right")})
	_paragraph_shading(p_pr, theme["surface"])
	fmt = paragraph.paragraph_format
	fmt.space_before = Pt(6)
	fmt.space_after = Pt(10)
	fmt.line_spacing = 1.0
	fmt.left_indent = Pt(6)
	fmt.right_indent = Pt(6)
	for index, line in enumerate(text.split("\n")):
		if index:
			paragraph.add_run().add_break()
		# Leading spaces must survive: python-docx writes xml:space="preserve".
		run = paragraph.add_run(line.replace("\t", "    "))
		_set_rfonts(run._r.get_or_add_rPr(), MONO_FONT)
		run.font.size = Pt(tokens.CODE_SIZE_PT)


def _all_descendant_text_raw(node: _Node) -> str:
	"""Like _all_descendant_text but without stripping, for <pre>."""
	segments = []
	for kind, value, _fmt in node._ordered_parts:
		if kind == "text":
			segments.append(value)
		elif value.tag != "img":
			segments.append(_all_descendant_text_raw(value))
	return "".join(segments)


def _add_rule(container, theme: dict) -> None:
	"""hr: an empty paragraph with a hairline bottom border, not underscores."""
	paragraph = container.add_paragraph()
	_paragraph_borders(paragraph._p.get_or_add_pPr(), theme["rule"], {"bottom": (6, 1)})
	paragraph.paragraph_format.space_before = Pt(6)
	paragraph.paragraph_format.space_after = Pt(12)


def _apply_table_borders(table, color: str) -> None:
	borders = OxmlElement("w:tblBorders")
	for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
		borders.append(_border_el(f"w:{edge}", color, 4, 0))
	_insert_ordered(table._tbl.tblPr, borders, _TBL_PR_ORDER)


def _set_table_cell_margins(table) -> None:
	margins = OxmlElement("w:tblCellMar")
	for edge, twips in (("top", 70), ("left", 110), ("bottom", 70), ("right", 110)):
		el = OxmlElement(f"w:{edge}")
		el.set(qn("w:w"), str(twips))
		el.set(qn("w:type"), "dxa")
		margins.append(el)
	_insert_ordered(table._tbl.tblPr, margins, _TBL_PR_ORDER)


def _repeat_as_header_row(row) -> None:
	tr_pr = row._tr.get_or_add_trPr()
	header = OxmlElement("w:tblHeader")
	_insert_ordered(tr_pr, header, _TR_PR_ORDER)


def _numbering_state(container, theme: dict) -> dict:
	"""Create (once per document) one bullet and one ordered abstract
	numbering definition in numbering.xml; return the shared state."""
	state = theme.get("_numbering")
	if state is not None:
		return state
	from docx.oxml import parse_xml
	from docx.oxml.ns import nsdecls

	numbering = container.part.numbering_part.element
	existing_abstract = [int(el.get(qn("w:abstractNumId"))) for el in numbering.findall(qn("w:abstractNum"))]
	existing_num = [int(el.get(qn("w:numId"))) for el in numbering.findall(qn("w:num"))]
	bullet_abstract = max([*existing_abstract, 0]) + 1
	ordered_abstract = bullet_abstract + 1

	def abstract_xml(abstract_id: int, ordered: bool) -> str:
		levels = []
		for ilvl in range(9):
			left = 540 + 360 * ilvl
			if ordered:
				fmt, text = _ORDERED_FORMATS[ilvl % len(_ORDERED_FORMATS)]
				text = text.format(n=ilvl + 1)
			else:
				fmt, text = "bullet", _BULLET_GLYPHS[ilvl % len(_BULLET_GLYPHS)]
			levels.append(
				f'<w:lvl w:ilvl="{ilvl}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/>'
				f'<w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
				f'<w:pPr><w:ind w:left="{left}" w:hanging="300"/></w:pPr>'
				f'<w:rPr><w:rFonts w:ascii="{BODY_FONT}" w:hAnsi="{BODY_FONT}" w:cs="{BODY_FONT}" w:hint="default"/></w:rPr>'
				f"</w:lvl>"
			)
		return (
			f'<w:abstractNum {nsdecls("w")} w:abstractNumId="{abstract_id}">'
			f'<w:multiLevelType w:val="hybridMultilevel"/>{"".join(levels)}</w:abstractNum>'
		)

	first_num = numbering.find(qn("w:num"))
	for abstract_id, ordered in ((bullet_abstract, False), (ordered_abstract, True)):
		element = parse_xml(abstract_xml(abstract_id, ordered))
		if first_num is not None:
			first_num.addprevious(element)
		else:
			numbering.append(element)

	state = {
		"numbering": numbering,
		"bullet_abstract": bullet_abstract,
		"ordered_abstract": ordered_abstract,
		"next_num": max([*existing_num, 0]) + 1,
		"bullet_num": None,
	}
	theme["_numbering"] = state
	return state


def _new_list_num(container, theme: dict, ordered: bool) -> int:
	from docx.oxml import parse_xml
	from docx.oxml.ns import nsdecls

	state = _numbering_state(container, theme)
	if not ordered and state["bullet_num"] is not None:
		return state["bullet_num"]
	num_id = state["next_num"]
	state["next_num"] += 1
	abstract_id = state["ordered_abstract"] if ordered else state["bullet_abstract"]
	overrides = ""
	if ordered:
		overrides = "".join(
			f'<w:lvlOverride w:ilvl="{ilvl}"><w:startOverride w:val="1"/></w:lvlOverride>' for ilvl in range(9)
		)
	state["numbering"].append(
		parse_xml(
			f'<w:num {nsdecls("w")} w:numId="{num_id}"><w:abstractNumId w:val="{abstract_id}"/>{overrides}</w:num>'
		)
	)
	if not ordered:
		state["bullet_num"] = num_id
	return num_id


def _set_numbering(paragraph, num_id: int, level: int) -> None:
	num_pr = paragraph._p.get_or_add_pPr().get_or_add_numPr()
	num_pr.get_or_add_ilvl().val = level
	num_pr.get_or_add_numId().val = num_id


def _add_default_footer(doc, theme: dict) -> None:
	"""Page numbers on every page (centred "Page X of Y"), unless the author
	supplied a running doc-footer, which already carries them."""
	footer = doc.sections[0].footer
	if any(p.text.strip() for p in footer.paragraphs):
		return
	footer.is_linked_to_previous = False
	paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
	paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
	paragraph.add_run("Page ")
	_add_field_run(paragraph, "PAGE")
	paragraph.add_run(" of ")
	_add_field_run(paragraph, "NUMPAGES")
	for run in paragraph.runs:
		run.font.size = Pt(tokens.CAPTION_SIZE_PT)
		run.font.color.rgb = _rgb_color(theme["muted"])


#: Fixed timestamp for every zip entry (the zip format's own epoch). python-docx
#: stamps entries with the current time, which made two renders of the same
#: document differ byte for byte - so a preview could never be proven to be
#: the exact file Export saves.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def _deterministic_zip(data: bytes) -> bytes:
	import zipfile

	source = zipfile.ZipFile(io.BytesIO(data))
	out = io.BytesIO()
	with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
		for info in source.infolist():
			entry = zipfile.ZipInfo(info.filename, date_time=_ZIP_EPOCH)
			entry.compress_type = zipfile.ZIP_DEFLATED
			entry.external_attr = 0o644 << 16
			target.writestr(entry, source.read(info.filename))
	return out.getvalue()


def _docx_hex(value: str) -> str:
	"""Strip a leading ``#`` for OOXML consumers. ``THEME`` (components.py)
	stores colours as ``#RRGGBB`` to match CSS, but ``w:fill``/``w:color``
	XML attributes and ``RGBColor.from_string`` both expect bare 6-digit hex
	with no ``#`` - ``RGBColor.from_string("#2C5AA8")`` raises outright
	(confirmed: ``ValueError: invalid literal for int() with base 16: '#2'``
	on the leading pair). Every colour reaching this module now comes from
	``resolve_theme_token``, which returns ``THEME``'s ``#``-prefixed form
	verbatim, so this normalisation has to sit centrally rather than at each
	call site.
	"""
	return value.lstrip("#")


def _rgb_color(hex_value: str) -> RGBColor:
	try:
		return RGBColor.from_string(_docx_hex(hex_value))
	except (ValueError, TypeError, AttributeError):
		return RGBColor.from_string(_docx_hex(SAFE_DEFAULT_COLOR))


def _shade_cell(cell, hex_color: str) -> None:
	"""Shade a table cell's background via a <w:shd> element on its tcPr -
	python-docx has no public cell-shading API.
	"""
	if not hasattr(cell, "_tc"):
		return
	tc_pr = cell._tc.get_or_add_tcPr()
	# Replace, never stack: a data-table header is shaded by the plain table
	# walker and again by the component recipe, and two <w:shd> children is
	# schema-invalid.
	for existing in tc_pr.findall(qn("w:shd")):
		tc_pr.remove(existing)
	shd = OxmlElement("w:shd")
	shd.set(qn("w:val"), "clear")
	shd.set(qn("w:color"), "auto")
	shd.set(qn("w:fill"), _docx_hex(hex_color))
	_insert_ordered(tc_pr, shd, _TC_PR_ORDER)


def _shade_run(run, hex_color: str) -> None:
	"""Shade a single run's background via a <w:shd> element on its rPr -
	OOXML supports run-level shading (unlike cell shading, python-docx has
	no wrapper for this either), which is what gives the "status-badge"
	recipe its filled-pill look in Word. Tested in Word/LibreOffice: a
	<w:shd> on rPr renders as a solid highlight behind just that run's
	text, distinct from (and independent of) the paragraph's own shading.
	"""
	r_pr = run._r.get_or_add_rPr()
	for existing in r_pr.findall(qn("w:shd")):
		r_pr.remove(existing)
	shd = OxmlElement("w:shd")
	shd.set(qn("w:val"), "clear")
	shd.set(qn("w:color"), "auto")
	shd.set(qn("w:fill"), _docx_hex(hex_color))
	_insert_ordered(r_pr, shd, _R_PR_ORDER)


def _set_table_borders(table, visible: bool, rule_color: str = THEME["rule"]) -> None:
	"""Turn a table's borders on (the built-in "Table Grid" style) or fully
	off via an explicit <w:tblBorders> with val="nil" on every edge -
	python-docx's default table has no guaranteed borderless style name, so
	"off" is expressed directly in XML rather than relying on one.
	"""
	if visible:
		table.style = "Table Grid"
		# Explicit borders too: the "Table Grid" style alone is invisible in
		# renderers that ignore table styles (macOS Quick Look / TextEdit
		# showed the sample's table with no lines at all).
		_apply_table_borders(table, rule_color)
		return

	tbl_pr = table._tbl.tblPr
	borders = OxmlElement("w:tblBorders")
	for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
		edge_el = OxmlElement(f"w:{edge}")
		edge_el.set(qn("w:val"), "nil")
		borders.append(edge_el)
	_insert_ordered(tbl_pr, borders, _TBL_PR_ORDER)


def _set_table_widths(table, theme: dict, ratios: list[float] | None = None) -> None:
	"""Disable autofit and give a table explicit widths that sum to the
	page's available content width.

	Observed failure: python-docx leaves a freshly created table's autofit
	ON, so an unconstrained table (a data-table nested in a .split cell, in
	the case actually seen) computed a width wider than its container and
	Word clipped the final column mid-word while the sidebar painted over
	the top of it. The split is linearised now (see the "passthrough"
	recipe type), but the same autofit default risks the same overflow for
	ANY table this renderer builds - data-table, synthetic tables
	(doc-header/callout/split-side), and the metric-grid alike - so every
	call site sets widths here rather than patching just the one case that
	was observed.

	`ratios` (e.g. doc-header's implicit 2 equal columns, or a future
	recipe's [0.66, 0.34]) are honoured when a recipe supplies them;
	otherwise the content width is split evenly across the table's actual
	column count. Word also requires the width to be set on both the
	column AND every cell in that column for a fixed layout to stick -
	setting only one is a well-known python-docx gotcha.
	"""
	# `table.autofit = False` (python-docx) already gets-or-adds the
	# <w:tblLayout> element and sets w:type="fixed" on it - a second,
	# manually-created <w:tblLayout> here would be a duplicate, schema-
	# invalid child of <w:tblPr> (CT_TblPrBase permits exactly one), so this
	# relies on the setter rather than also emitting the element by hand.
	table.autofit = False

	num_cols = len(table.columns)
	if not num_cols:
		return

	content_width = theme.get("_content_width_emu") or _FALLBACK_CONTENT_WIDTH_EMU

	if ratios:
		col_widths = [Emu(int(content_width * ratio)) for ratio in ratios]
		# Defensive padding: a recipe's ratio list and the table's real
		# column count could disagree (e.g. overflow bucketing in
		# _render_synthetic_table put more logical children than "cols" into
		# the last physical cell, but never changes the physical column
		# count) - repeat the last ratio's width rather than leaving a
		# column with no explicit width at all.
		while len(col_widths) < num_cols:
			col_widths.append(col_widths[-1])
	else:
		equal_width = Emu(content_width // num_cols)
		col_widths = [equal_width] * num_cols

	# Total table width too (tblW): renderers that ignore column widths
	# (Quick Look) otherwise shrink the table to its content.
	tbl_w = OxmlElement("w:tblW")
	tbl_w.set(qn("w:w"), str(int(sum(col_widths[:num_cols]) / 635)))
	tbl_w.set(qn("w:type"), "dxa")
	_insert_ordered(table._tbl.tblPr, tbl_w, _TBL_PR_ORDER)

	for index in range(num_cols):
		width = col_widths[index]
		table.columns[index].width = width
		for row in table.rows:
			if index < len(row.cells):
				row.cells[index].width = width


def _clear_cell(cell) -> None:
	"""Remove a freshly-created table cell's single default empty paragraph
	so subsequent add_paragraph()/add_table() calls don't leave a stray
	blank line before the real content. Only ever called immediately before
	adding real content, so the cell is never left without any block child
	(which OOXML requires).
	"""
	if not cell.paragraphs:
		return
	paragraph = cell.paragraphs[0]
	if len(cell.paragraphs) == 1 and not paragraph.runs and not paragraph.text:
		element = paragraph._p
		element.getparent().remove(element)


def _document_content_width_emu(doc) -> int:
	"""EMU width of `doc`'s printable content area: page width minus the
	first section's left/right margins, read from the section's actual
	geometry rather than hardcoded - a template change (or any page size
	other than the current default) is honoured automatically. Computed
	once in html_to_docx and threaded through every render call via
	theme["_content_width_emu"] (the same vehicle already used to thread
	the document's colour palette everywhere), since only the top-level
	Document object can see section geometry - a table nested inside a
	cell has no way to ask "how wide is the page" on its own.
	"""
	section = doc.sections[0]
	return section.page_width - section.left_margin - section.right_margin


def html_to_docx(html: str) -> bytes:
	"""Convert the HTML produced by ``render_document_html()`` to a .docx file.

	Args:
		html: A full HTML document string as produced by
			``huf.ai.artifacts.render.html.render_document_html``.

	Returns:
		Raw bytes of a valid .docx file.
	"""
	builder = _BodyTreeBuilder()
	builder.feed(html)
	builder.close()

	# The document's effective palette: the registry defaults, updated with
	# whatever the author validly overrode in a <style> block's :root rule
	# (see _extract_theme). Computed once and threaded through every
	# _render_node()/recipe call below rather than re-parsed per component,
	# since the whole document shares one theme.
	theme = _extract_theme("".join(builder.style_text_parts))

	# The parser walks the whole document (including <head>/<style>), but
	# only tags from the sanitized vocabulary open nodes, so non-body content
	# (title, style rules) never produces nodes under root.
	doc = Document()
	_setup_document(doc, theme, builder.title.strip())
	# See _document_content_width_emu - stashed on theme (already threaded
	# to every _render_node/recipe call) rather than added as a new
	# parameter to every one of those functions, since the whole document
	# shares one content width just like it shares one palette.
	theme["_content_width_emu"] = _document_content_width_emu(doc)

	for node in builder.root.children:
		_render_node(doc, node, theme)

	_add_default_footer(doc, theme)

	buffer = io.BytesIO()
	doc.save(buffer)
	# Same input, same bytes: the contract the format preview relies on
	# (preview_document_file and export_document_content must hash-equal).
	return _deterministic_zip(buffer.getvalue())
