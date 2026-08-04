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

The HTML is walked with the stdlib ``html.parser.HTMLParser`` (not
BeautifulSoup) to keep this module dependency-free beyond python-docx.
"""

import base64
import io
import re
from html.parser import HTMLParser

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches


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

#: Block-level tags that terminate the "current" node when closed. Everything
#: else (inline tags, and stray tags outside the sanitized vocabulary) is
#: treated as text-bearing but does not open a new node in the tree.
_BLOCK_TAGS = {
	"p", "h1", "h2", "h3", "h4", "h5", "h6",
	"ul", "ol", "li",
	"table", "thead", "tbody", "tr", "th", "td",
	"blockquote", "hr", "pre",
	"div",
}

#: Container tags whose children must each render as their own separate docx
#: block, never flattened into a single joined string via full_text. div is
#: only ever used by render_document_html for a columns-N section wrapper -
#: a structural container, not a text-bearing leaf like p/blockquote.
_CONTAINER_TAGS = ("table", "thead", "tbody", "tr", "th", "td", "div")

#: Tags whose text (and descendant text) should be dropped from the parent's
#: rendered text rather than concatenated inline. None of the tags in the
#: sanitized vocabulary need this, but "script"/"style" are excluded
#: defensively in case they ever slip through.
_IGNORED_TEXT_TAGS = {"script", "style"}


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

	def add_text(self, data: str) -> None:
		self.text_parts.append(data)

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

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		if tag in _IGNORED_TEXT_TAGS:
			self._ignored_depth += 1
			return
		if self._ignored_depth:
			return

		attr_dict = {key: (value or "") for key, value in attrs}

		if tag in _BLOCK_TAGS:
			node = _Node(tag, attr_dict, parent=self._current)
			self._current.children.append(node)
			self._current = node
		elif tag == "img":
			# img is a void element (no matching handle_endtag) — record it as
			# a leaf child of the current node so text order is preserved.
			node = _Node(tag, attr_dict, parent=self._current)
			self._current.children.append(node)
		elif tag == "br":
			self._current.add_text("\n")
		# Other inline tags (strong, em, a, span, div, code) don't need their
		# own node — their text is folded into the enclosing block's text.

	def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		if tag == "img":
			self.handle_starttag(tag, attrs)
		elif tag == "br":
			self.handle_starttag(tag, attrs)
		elif tag == "hr":
			self.handle_starttag(tag, attrs)
			self.handle_endtag(tag)

	def handle_endtag(self, tag: str) -> None:
		if tag in _IGNORED_TEXT_TAGS:
			self._ignored_depth = max(0, self._ignored_depth - 1)
			return
		if self._ignored_depth:
			return

		if tag in _BLOCK_TAGS and self._current.tag == tag:
			self._current = self._current.parent or self.root

	def handle_data(self, data: str) -> None:
		if self._ignored_depth:
			return
		self._current.add_text(data)


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


def _add_image(doc: Document, node: _Node) -> None:
	src = node.attrs.get("src") or ""
	if not src.startswith("data:"):
		# http(s) URLs (or anything else) are skipped — no network calls.
		return

	try:
		header, _, encoded = src.partition(",")
		if ";base64" not in header:
			return
		image_bytes = base64.b64decode(encoded)
		doc.add_picture(io.BytesIO(image_bytes))
	except Exception:
		# Best-effort: a malformed data URI should not crash the export.
		pass


def _add_table(doc: Document, table_node: _Node) -> None:
	rows: list[list[_Node]] = []
	for section in table_node.children:
		if section.tag in ("thead", "tbody"):
			for tr in section.children:
				if tr.tag == "tr":
					rows.append([cell for cell in tr.children if cell.tag in ("th", "td")])
		elif section.tag == "tr":
			rows.append([cell for cell in section.children if cell.tag in ("th", "td")])

	if not rows:
		return

	num_cols = max(len(row) for row in rows)
	table = doc.add_table(rows=len(rows), cols=num_cols)
	table.style = "Table Grid"

	for row_index, row in enumerate(rows):
		for col_index, cell_node in enumerate(row):
			table.cell(row_index, col_index).text = cell_node.full_text


def _add_list(doc: Document, list_node: _Node, style: str) -> None:
	for item in list_node.children:
		if item.tag == "li":
			doc.add_paragraph(item.full_text, style=style)


def _render_node(doc: Document, node: _Node) -> None:
	tag = node.tag

	if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
		level = int(tag[1])
		doc.add_heading(node.full_text, level=level)
	elif tag == "p":
		if node.children and all(child.tag == "img" for child in node.children) and not node.full_text:
			for child in node.children:
				_add_image(doc, child)
			return
		paragraph = doc.add_paragraph(node.full_text)
		_apply_alignment_and_indent(paragraph, node)
	elif tag == "blockquote":
		paragraph = doc.add_paragraph(node.full_text, style="Intense Quote")
		_apply_alignment_and_indent(paragraph, node)
	elif tag == "ul":
		_add_list(doc, node, "List Bullet")
	elif tag == "ol":
		_add_list(doc, node, "List Number")
	elif tag == "table":
		_add_table(doc, node)
	elif tag == "pre":
		doc.add_paragraph(node.full_text)
	elif tag == "hr":
		doc.add_paragraph("_" * 40)
	elif tag == "img":
		_add_image(doc, node)
	elif tag == "div":
		_render_div(doc, node)
	# thead/tbody/tr/th/td/li are handled by their container (table/ul/ol)
	# and should never appear as direct children of the root.


_COLUMNS_CLASS_RE = re.compile(r"^columns-([23])$")


def _render_div(doc: Document, node: _Node) -> None:
	"""Render a <div> — currently only used by render_document_html for a
	``columns-N`` section wrapper. A div without a recognised columns class
	renders as a plain passthrough (its children rendered inline, no section
	change), so future non-columns div usage degrades gracefully rather than
	silently dropping content.
	"""
	column_count = None
	for class_name in node.classes():
		match = _COLUMNS_CLASS_RE.match(class_name)
		if match:
			column_count = int(match.group(1))
			break

	if column_count is None:
		for child in node.children:
			_render_node(doc, child)
		return

	_set_section_columns(doc.add_section(WD_SECTION.CONTINUOUS), column_count)
	for child in node.children:
		_render_node(doc, child)
	# Close the columns region: a fresh CONTINUOUS section reset to a single
	# column, so content after the div returns to normal single-column flow
	# rather than inheriting the multi-column layout indefinitely.
	_set_section_columns(doc.add_section(WD_SECTION.CONTINUOUS), 1)


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

	# The parser walks the whole document (including <head>/<style>), but
	# only tags from the sanitized vocabulary open nodes, so non-body content
	# (title, style rules) never produces nodes under root.
	doc = Document()

	for node in builder.root.children:
		_render_node(doc, node)

	buffer = io.BytesIO()
	doc.save(buffer)
	return buffer.getvalue()
