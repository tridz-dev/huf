"""Regression tests for the document render pipeline (HTML -> PDF/DOCX).

Every assertion here corresponds to a defect observed in a real exported
document, not to a hypothetical. The pipeline had no tests before this file,
and the bugs it pins were all silent - the export succeeded and simply came
out wrong, so nothing surfaced them until a human compared a PDF against a
Word file side by side.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_document_render
"""

import re
import unittest
import zipfile
from io import BytesIO

from huf.ai.artifacts.render.components import (
	COMPONENTS,
	THEME,
	components_css,
	resolve_theme_token,
	theme_css,
)
from huf.ai.artifacts.render.docx import html_to_docx
from huf.ai.artifacts.render.html import _hoist_running_footer, render_document_html


def _docx_part(docx_bytes: bytes, name_fragment: str) -> str:
	"""Concatenate every part of the .docx zip whose name contains a fragment."""
	with zipfile.ZipFile(BytesIO(docx_bytes)) as archive:
		return "".join(
			archive.read(entry).decode("utf-8")
			for entry in archive.namelist()
			if name_fragment in entry
		)


class TestComponentRegistry(unittest.TestCase):
	"""The registry is the anti-drift mechanism; these guard the invariants
	the PDF and DOCX renderers both depend on."""

	def test_every_component_defines_both_renderers(self):
		"""A component with only a "css" key styles the PDF and silently
		vanishes from Word - the exact class of bug this registry exists to
		make impossible."""
		for class_name, component in COMPONENTS.items():
			self.assertIn("css", component, f"{class_name} has no css")
			self.assertIn("docx", component, f"{class_name} has no docx recipe")

	def test_stylesheet_order_is_deterministic(self):
		"""components_css() once iterated a frozenset, so rule order changed
		between processes and two same-specificity rules could win on
		different runs. Order must be stable."""
		self.assertEqual(components_css(), components_css())

	def test_colours_live_only_in_the_theme_block(self):
		"""Every colour must reach CSS through a custom property. A literal
		hex in a component rule is invisible to an author's :root override,
		so the PDF would re-theme while that one rule did not."""
		css = components_css()
		root_block = css[: css.index("}") + 1]
		component_rules = css[css.index("}") + 1 :]

		self.assertIn(":root", root_block)
		self.assertEqual(
			re.findall(r"#[0-9A-Fa-f]{3,8}", component_rules),
			[],
			"component CSS contains a literal colour; use var(--token)",
		)

	def test_recipe_colours_are_theme_references(self):
		"""Same invariant on the DOCX side: a hardcoded hex in a recipe is
		how a re-themed document produced a blue Word file from a red PDF."""
		colour_keys = ("color", "shading", "header_shading", "header_color", "value_color", "label_color")
		for class_name, component in COMPONENTS.items():
			for key in colour_keys:
				value = component["docx"].get(key)
				if value:
					self.assertTrue(
						value.startswith("var(--"),
						f"{class_name}.{key} is a literal colour: {value}",
					)

	def test_resolve_theme_token(self):
		self.assertEqual(resolve_theme_token("var(--accent)"), THEME["accent"])
		self.assertEqual(resolve_theme_token("var(--accent)", {"accent": "#D32F2F"}), "#D32F2F")
		self.assertEqual(resolve_theme_token("Table Grid"), "Table Grid")

	def test_theme_css_declares_every_token(self):
		css = theme_css()
		for token in THEME:
			self.assertIn(f"--{token}:", css)


class TestRunningFooterHoist(unittest.TestCase):
	"""A CSS running element only applies to the page it sits on and every
	page after it. Authors write footers last, so an un-hoisted footer
	appears on the final page alone - verified against WeasyPrint 68."""

	def test_footer_written_last_moves_to_front(self):
		body = '<h1>T</h1><p>body</p><p class="doc-footer">CONFIDENTIAL</p>'
		self.assertTrue(_hoist_running_footer(body).startswith('<p class="doc-footer">'))

	def test_hoist_is_a_pure_reorder(self):
		"""Nothing may be added or lost - only moved."""
		cases = [
			'<h1>T</h1><p class="doc-footer">F</p>',
			'<p>a</p><div class="doc-footer"><div>inner</div>tail</div><p>b</p>',
			'<p>x</p><footer class="doc-footer small">F</footer>',
			'<p class="doc-footer">F</p><p>body</p>',
		]
		for body in cases:
			self.assertEqual(sorted(_hoist_running_footer(body)), sorted(body), body)

	def test_nested_same_tag_balances(self):
		body = '<p>a</p><div class="doc-footer"><div>inner</div>tail</div><p>b</p>'
		self.assertTrue(
			_hoist_running_footer(body).startswith('<div class="doc-footer"><div>inner</div>tail</div>')
		)

	def test_unbalanced_markup_is_left_alone(self):
		"""A wrong slice would corrupt the body. A footer on one page is a
		far smaller defect than mangled HTML."""
		body = '<p>a</p><div class="doc-footer">oops'
		self.assertEqual(_hoist_running_footer(body), body)

	def test_no_footer_is_a_no_op(self):
		self.assertEqual(_hoist_running_footer("<p>body</p>"), "<p>body</p>")


class TestPrintStylesheet(unittest.TestCase):
	def setUp(self):
		self.document = render_document_html("<p>hi</p>", title="T", language="html")

	def test_screen_padding_is_media_scoped(self):
		"""The preview iframe ignores @page, so body needs padding on screen.
		It MUST stay inside @media screen: WeasyPrint renders print media, so
		an unscoped rule would stack on top of the 2cm @page margin and give
		the PDF a 4cm margin."""
		self.assertIn("@media screen", self.document)
		screen_block = self.document[self.document.index("@media screen") :]
		self.assertIn("padding: 2cm", screen_block[: screen_block.index("}")])

	def test_page_number_uses_total_count(self):
		"""Authors hand-wrote "PAGE 1 OF 2" and it was wrong the moment
		pagination shifted."""
		self.assertIn("counter(pages)", self.document)

	def test_running_footer_is_pulled_into_the_margin_box(self):
		self.assertIn("element(foot)", self.document)
		self.assertIn("running(foot)", self.document)

	def test_running_footer_is_hidden_on_screen(self):
		"""`running(foot)` only lifts the footer out of flow in PAGED media.
		A browser ignores it, so the hoisted element (moved to the top of the
		body so the PDF repeats it on every page) rendered as the FIRST line
		of the preview - a document opened in the artifact pane led with
		"CONFIDENTIAL - PAGE 1 OF 2" above its own letterhead.

		Verified in a real browser: without this the computed display was
		`flex`, taken from the AUTHOR's <style> block. Hence !important - an
		author's rules sit later in the cascade and win at equal specificity.
		The rule must stay inside @media screen so the PDF keeps its footer.
		"""
		screen_block = self.document[self.document.index("@media screen {") :]
		screen_block = screen_block[: screen_block.index("\n}\n\nh1")]

		self.assertIn(".doc-footer", screen_block)
		self.assertIn("display: none !important", screen_block)

	def test_author_styles_cannot_unhide_the_screen_footer(self):
		"""The regression itself: an author setting `display: flex` on
		.doc-footer must not put the footer back into the preview flow.

		The author's <style> survives sanitization into the BODY, i.e. after
		the platform stylesheet in </head>, so it wins any equal-specificity
		contest. Only !important on the platform side beats it - that is the
		property this test pins.
		"""
		author_css = ".doc-footer { display: flex; }"
		document = render_document_html(
			f"<style>{author_css}</style>"
			'<p>Body.</p><p class="doc-footer">CONFIDENTIAL</p>',
			language="html",
		)

		head_end = document.index("</head>")
		platform_rule = document.index("display: none !important")
		author_rule = document.index(author_css)

		# The author's rule really does land later in the cascade...
		self.assertLess(platform_rule, head_end)
		self.assertGreater(author_rule, head_end)
		# ...so the platform rule can only win by being !important.
		self.assertIn("display: none !important", document[:head_end])


class TestDocxExport(unittest.TestCase):
	"""Each test here is a document that exported successfully while losing
	content or colour."""

	def test_callout_inline_content_survives(self):
		"""_render_synthetic_table built cells only from child NODES. A
		callout holding just <strong> plus tail text has no child nodes, so
		the executive summary silently vanished from the Word file."""
		html = render_document_html(
			'<div class="callout"><strong>Executive Summary:</strong> revenue up 18.4%.</div>',
			language="html",
		)
		body = _docx_part(html_to_docx(html), "word/document.xml")
		self.assertIn("Executive Summary", body)
		self.assertIn("revenue up 18.4%", body)

	def test_metric_value_survives_a_wrapper_element(self):
		"""_render_metric_value_cell read only the node's own text, so a
		value wrapped in any element landed on a child node and disappeared,
		leaving a card with a label and no number."""
		html = render_document_html(
			'<div class="metric-grid">'
			'<div class="metric" data-label="TARGET REVENUE"><div>$12.5M</div></div>'
			'<div class="metric" data-label="GROWTH">+34%</div>'
			"</div>",
			language="html",
		)
		body = _docx_part(html_to_docx(html), "word/document.xml")
		self.assertIn("$12.5M", body)
		self.assertIn("+34%", body)
		self.assertIn("TARGET REVENUE", body)

	def test_author_theme_reaches_word(self):
		"""The defect that started this: an author re-themed to red, the PDF
		obeyed and the DOCX stayed registry blue - one document, two colour
		schemes."""
		html = render_document_html(
			'<style>:root { --accent: #D32F2F; }</style>'
			'<header class="doc-header"><span class="brand">ACME</span></header>',
			language="html",
		)
		body = _docx_part(html_to_docx(html), "word/document.xml")
		self.assertIn("D32F2F", body)
		self.assertNotIn(THEME["accent"].lstrip("#"), body)

	def test_malformed_theme_falls_back_to_defaults(self):
		"""A hostile or broken <style> block must degrade, never raise."""
		for style in (
			"<style>:root { --accent: not-a-colour; }</style>",
			"<style>:root { --accent: </style>",
			"<style>@@@ garbage {{{</style>",
			"<style>:root { --gap: 8pt; }</style>",
		):
			html = render_document_html(f'{style}<span class="brand">ACME</span>', language="html")
			body = _docx_part(html_to_docx(html), "word/document.xml")
			self.assertIn(THEME["accent"].lstrip("#"), body, style)

	def test_stylesheet_does_not_leak_into_the_body(self):
		"""The chat once rendered a document as a wall of raw CSS; the DOCX
		must never do the same."""
		html = render_document_html(
			'<style>:root { --accent: #D32F2F; } .x { font-family: Inter; }</style><p>Body text.</p>',
			language="html",
		)
		body = _docx_part(html_to_docx(html), "word/document.xml")
		self.assertIn("Body text.", body)
		self.assertNotIn("font-family", body)
		self.assertNotIn(":root", body)

	def test_footer_becomes_a_real_word_footer(self):
		"""Written once in the body, it must repeat on every page via the
		footer part - not sit mid-flow as an ordinary paragraph."""
		docx_bytes = html_to_docx(
			render_document_html(
				'<p>Body.</p><p class="doc-footer">CONFIDENTIAL</p>', language="html"
			)
		)
		self.assertIn("CONFIDENTIAL", _docx_part(docx_bytes, "word/footer"))
		self.assertNotIn("CONFIDENTIAL", _docx_part(docx_bytes, "word/document.xml"))

	def test_page_break_emits_a_real_break(self):
		html = render_document_html(
			'<p>One.</p><div class="page-break"></div><p>Two.</p>', language="html"
		)
		body = _docx_part(html_to_docx(html), "word/document.xml")
		self.assertIn('w:type="page"', body)

	def test_split_is_linearised_not_nested(self):
		"""DOCX carries content, the PDF carries the design. A .split mapped
		to a two-column table put a data-table inside a table cell, and Word
		clipped the inner table's last column mid-word while the sidebar
		painted over it. The sidebar now flows below the main content."""
		html = render_document_html(
			'<div class="split">'
			'<section class="split-main"><table class="data-table">'
			"<tr><th>Pillar</th><th>Status</th></tr><tr><td>Cloud</td><td>Live</td></tr>"
			"</table></section>"
			'<aside class="split-side"><h3>Key Snapshot</h3><p>Enterprise Tech</p></aside>'
			"</div>",
			language="html",
		)
		body = _docx_part(html_to_docx(html), "word/document.xml")

		self.assertNotIn("<w:tbl>", body.split("<w:tbl>", 1)[1].split("</w:tbl>", 1)[0])
		self.assertIn("Key Snapshot", body)
		self.assertIn("Enterprise Tech", body)

	def test_tables_have_fixed_widths(self):
		"""Autofit let an inner table compute a width wider than its
		container, which is what Word clipped."""
		html = render_document_html(
			'<table class="data-table"><tr><th>A</th><th>B</th></tr></table>', language="html"
		)
		body = _docx_part(html_to_docx(html), "word/document.xml")

		self.assertEqual(body.count("<w:tbl>"), body.count('w:type="fixed"'))

	def test_headings_take_the_theme_colour(self):
		"""Word's built-in Heading styles carry their own blue, so a themed
		document came out with a correct brand colour and blue headings -
		reading as though the theme had not applied at all."""
		html = render_document_html(
			"<style>:root { --ink: #121212; }</style>"
			'<h1 class="doc-title">Title</h1><h3>Section</h3>',
			language="html",
		)
		body = _docx_part(html_to_docx(html), "word/document.xml")

		self.assertIn('w:val="121212"', body)

	def test_status_badge_text_is_not_dropped(self):
		"""Plain-table cells assigned cell.text from a block-filtered walk,
		so an inline badge inside a table cell was discarded entirely."""
		html = render_document_html(
			"<table><tr><td>Cloud</td>"
			'<td><span class="status-badge">In Progress</span></td></tr></table>',
			language="html",
		)
		body = _docx_part(html_to_docx(html), "word/document.xml")
		self.assertIn("In Progress", body)
