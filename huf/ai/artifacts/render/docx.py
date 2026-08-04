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
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from huf.ai.artifacts.render.components import COMPONENTS, COMPONENT_CLASSES


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

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		if tag in _IGNORED_TEXT_TAGS:
			self._ignored_depth += 1
			return
		if self._ignored_depth:
			return

		attr_dict = {key: (value or "") for key, value in attrs}

		if _opens_node(tag, attr_dict):
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
			self.handle_endtag(tag)

	def handle_endtag(self, tag: str) -> None:
		if tag in _IGNORED_TEXT_TAGS:
			self._ignored_depth = max(0, self._ignored_depth - 1)
			return
		if self._ignored_depth:
			return

		# self._current.tag can only equal `tag` here if a node was actually
		# opened for it (see _opens_node) — a plain <span> or <strong> never
		# becomes `self._current`, so its close tag is a no-op, same as before.
		if self._current is not self.root and self._current.tag == tag:
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
		paragraph.add_run().add_picture(io.BytesIO(image_bytes))
	except Exception:
		# Best-effort: a malformed data URI should not crash the export.
		pass


def _add_table(container, table_node: _Node):
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

	for row_index, row in enumerate(rows):
		for col_index, cell_node in enumerate(row):
			table.cell(row_index, col_index).text = cell_node.full_text

	return table


def _add_list(container, list_node: _Node, style: str) -> None:
	for item in list_node.children:
		if item.tag == "li":
			container.add_paragraph(item.full_text, style=style)


def _render_node(container, node: _Node) -> None:
	class_name, recipe = _component_recipe(node)
	if recipe is not None:
		_render_component(container, node, class_name, recipe)
		return

	tag = node.tag

	if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
		level = int(tag[1])
		_add_heading(container, node.full_text, level)
	elif tag == "p":
		if node.children and all(child.tag == "img" for child in node.children) and not node.full_text:
			for child in node.children:
				_add_image(container, child)
			return
		paragraph = container.add_paragraph(node.full_text)
		_apply_alignment_and_indent(paragraph, node)
	elif tag == "blockquote":
		paragraph = container.add_paragraph(node.full_text, style="Intense Quote")
		_apply_alignment_and_indent(paragraph, node)
	elif tag == "ul":
		_add_list(container, node, "List Bullet")
	elif tag == "ol":
		_add_list(container, node, "List Number")
	elif tag == "table":
		_add_table(container, node)
	elif tag == "pre":
		container.add_paragraph(node.full_text)
	elif tag == "hr":
		container.add_paragraph("_" * 40)
	elif tag == "img":
		_add_image(container, node)
	elif tag == "div":
		_render_div(container, node)
	elif node.children:
		# Unclassed/unknown container tag - degrade gracefully by rendering
		# children in document order rather than dropping them.
		for child in node.children:
			_render_node(container, child)
	# thead/tbody/tr/th/td/li are handled by their container (table/ul/ol)
	# and should never appear as direct children of the root.


_COLUMNS_CLASS_RE = re.compile(r"^columns-([23])$")


def _render_div(container, node: _Node) -> None:
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
			_render_node(container, child)
		return

	_set_section_columns(container.add_section(WD_SECTION.CONTINUOUS), column_count)
	for child in node.children:
		_render_node(container, child)
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


def _render_component(container, node: _Node, class_name: str, recipe: dict) -> None:
	kind = recipe.get("type")
	if kind == "table":
		_render_table_recipe(container, node, recipe)
	elif kind == "table_row_of_cells":
		_render_metric_grid(container, node, recipe)
	elif kind == "cell":
		_render_cell_recipe(container, node, recipe)
	elif kind == "run":
		_render_run_recipe(container, node, recipe)
	elif kind == "paragraph":
		_render_paragraph_recipe(container, node, recipe)
	elif kind == "heading":
		_render_heading_recipe(container, node, recipe)
	else:
		# Unknown recipe type: degrade gracefully rather than drop content.
		for child in node.children:
			_render_node(container, child)


def _render_table_recipe(container, node: _Node, recipe: dict) -> None:
	"""type: "table". Two shapes, distinguished by the recipe itself:

	- Has "cols": the class is on an arbitrary container (div) whose direct
	  children become the table's cells (doc-header, callout, split).
	- No "cols": the class is on a real sanitized <table> (data-table) - the
	  existing row/cell walker builds the table, this only adds header
	  shading on top.
	"""
	if "cols" in recipe:
		_render_synthetic_table(container, node, recipe)
	else:
		_render_data_table(container, node, recipe)


def _render_data_table(container, node: _Node, recipe: dict) -> None:
	table = _add_table(container, node)
	if table is None or not table.rows:
		return

	header_shading = recipe.get("header_shading")
	header_color = recipe.get("header_color")
	for cell in table.rows[0].cells:
		if header_shading:
			_shade_cell(cell, header_shading)
		if header_color:
			for paragraph in cell.paragraphs:
				for run in paragraph.runs:
					run.font.color.rgb = RGBColor.from_string(header_color)
					run.font.bold = True


def _render_synthetic_table(container, node: _Node, recipe: dict) -> None:
	cols = recipe["cols"]

	# Assign each direct child its own cell in document order; if there are
	# more children than columns (or exactly one column, e.g. callout), the
	# overflow lands in the last cell together rather than being dropped.
	cell_children: list[list[_Node]] = [[] for _ in range(cols)]
	for index, child in enumerate(node.children):
		cell_children[min(index, cols - 1)].append(child)

	table = container.add_table(rows=1, cols=cols)
	_set_table_borders(table, recipe.get("borders", True))

	widths = recipe.get("widths")
	if widths:
		_set_column_widths(table, widths)

	shading = recipe.get("shading")
	col_align = recipe.get("col_align")

	for col_index in range(cols):
		cell = table.cell(0, col_index)
		if shading and cols == 1:
			_shade_cell(cell, shading)

		contents = cell_children[col_index]
		if contents:
			_clear_cell(cell)
			for child in contents:
				_render_node(cell, child)

		if col_align and col_index < len(col_align):
			alignment = _ALIGNMENTS.get(f"text-{col_align[col_index]}")
			if alignment is not None:
				for paragraph in cell.paragraphs:
					paragraph.alignment = alignment


def _render_metric_grid(container, node: _Node, recipe: dict) -> None:
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

	for index, metric_node in enumerate(metrics):
		row_index, col_index = divmod(index, cols)
		cell = table.cell(row_index, col_index)
		# Cell clearing is owned by whichever component recipe fills the
		# cell (see _render_cell_recipe/_render_metric_value_cell) - not
		# done here too, since _clear_cell is only safe to call once on a
		# cell that still has its default empty paragraph.
		_render_node(cell, metric_node)


def _render_cell_recipe(container, node: _Node, recipe: dict) -> None:
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
		_render_metric_value_cell(container, node, recipe)
		return

	shading = recipe.get("shading")
	if shading:
		_shade_cell(container, shading)

	if node.children:
		_clear_cell(container)
		for child in node.children:
			_render_node(container, child)
	elif node.text:
		_clear_cell(container)
		container.add_paragraph(node.text)


def _render_metric_value_cell(container, node: _Node, recipe: dict) -> None:
	shading = recipe.get("shading")
	if shading:
		_shade_cell(container, shading)

	_clear_cell(container)

	value_paragraph = container.add_paragraph()
	value_run = value_paragraph.add_run(node.text)
	value_run.font.bold = True
	value_run.font.size = Pt(recipe["value_size_pt"])

	label_attr = recipe.get("label_from")
	label_text = node.attrs.get(label_attr, "") if label_attr else ""
	if label_text:
		label_paragraph = container.add_paragraph()
		label_run = label_paragraph.add_run(label_text)
		label_run.font.size = Pt(recipe["label_size_pt"])


def _render_run_recipe(container, node: _Node, recipe: dict) -> None:
	"""type: "run" (brand). A single bold/coloured run in its own paragraph."""
	paragraph = container.add_paragraph()
	run = paragraph.add_run(node.text)
	if recipe.get("bold"):
		run.font.bold = True
	color = recipe.get("color")
	if color:
		run.font.color.rgb = RGBColor.from_string(color)
	size_pt = recipe.get("size_pt")
	if size_pt:
		run.font.size = Pt(size_pt)


def _render_paragraph_recipe(container, node: _Node, recipe: dict) -> None:
	"""type: "paragraph" (doc-meta, doc-subtitle, doc-footer)."""
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
			run.font.color.rgb = RGBColor.from_string(color)


def _render_heading_recipe(container, node: _Node, recipe: dict) -> None:
	"""type: "heading" (doc-title)."""
	_add_heading(container, node.full_text, recipe.get("level", 1))


def _shade_cell(cell, hex_color: str) -> None:
	"""Shade a table cell's background via a <w:shd> element on its tcPr -
	python-docx has no public cell-shading API.
	"""
	if not hasattr(cell, "_tc"):
		return
	tc_pr = cell._tc.get_or_add_tcPr()
	shd = OxmlElement("w:shd")
	shd.set(qn("w:val"), "clear")
	shd.set(qn("w:color"), "auto")
	shd.set(qn("w:fill"), hex_color)
	tc_pr.append(shd)


def _set_table_borders(table, visible: bool) -> None:
	"""Turn a table's borders on (the built-in "Table Grid" style) or fully
	off via an explicit <w:tblBorders> with val="nil" on every edge -
	python-docx's default table has no guaranteed borderless style name, so
	"off" is expressed directly in XML rather than relying on one.
	"""
	if visible:
		table.style = "Table Grid"
		return

	tbl_pr = table._tbl.tblPr
	borders = OxmlElement("w:tblBorders")
	for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
		edge_el = OxmlElement(f"w:{edge}")
		edge_el.set(qn("w:val"), "nil")
		borders.append(edge_el)
	tbl_pr.append(borders)


def _set_column_widths(table, ratios: list[float]) -> None:
	"""Apply proportional column widths (e.g. split's [0.66, 0.34]) against
	a fixed 6" reference width. Word requires the width to be set on both
	the column AND every cell in it for a fixed-width table to render
	correctly - setting only one is a well-known python-docx gotcha.
	"""
	table.autofit = False
	reference_width = 6.0
	for index, ratio in enumerate(ratios):
		width = Inches(reference_width * ratio)
		if index < len(table.columns):
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
