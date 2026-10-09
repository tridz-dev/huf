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
import time
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
from huf.ai.artifacts.render.html import (
	_dedent_markdown_containers,
	_hoist_running_footer,
	_in_ranges,
	_markdown_containers,
	_propagate_markdown_attr,
	render_document_html,
)


class TestRenderHardening(unittest.TestCase):
	def test_title_is_escaped(self):
		doc = render_document_html("<p>x</p>", title="</title><script>alert(1)</script>")
		self.assertNotIn("<script>alert(1)", doc)
		self.assertIn("&lt;/title&gt;", doc)

	def test_style_strips_remote_and_dangerous_css(self):
		src = (
			"<style>@import url('https://evil.test/a.css');"
			".a{background:url(https://evil.test/x.png)}"
			".b{background:url(//evil.test/x)}"
			".c{background:url(data:image/png;base64,AAAA)}"
			".d{width:expression(alert(1));behavior:url(x.htc)}"
			".ok{color:red;background:url(img/local.png)}</style><p>x</p>"
		)
		doc = render_document_html(src, title="t", language="html")
		# The built-in stylesheet legitimately @imports Google Fonts; check the body only.
		doc = doc.split("<body", 1)[1]
		for bad in ("evil.test", "@import", "data:image", "expression(", "behavior"):
			self.assertNotIn(bad, doc)
		self.assertIn(".ok{color:red;background:url(img/local.png)}", doc)

	def test_resolve_theme_token_fallbacks(self):
		from huf.ai.artifacts.render.components import SAFE_DEFAULT_COLOR, resolve_theme_token

		self.assertEqual(resolve_theme_token("var(--nope, #fff)"), "#fff")
		self.assertEqual(resolve_theme_token("var(--nope)"), SAFE_DEFAULT_COLOR)
		self.assertEqual(resolve_theme_token("var(--nope, var(--nope2))"), SAFE_DEFAULT_COLOR)
		self.assertEqual(resolve_theme_token("var(--accent)"), THEME["accent"])

	def test_docx_with_unknown_token_does_not_raise(self):
		html = render_document_html(
			'<p style="color: var(--missing)">hello</p><p style="color: var(--missing, #336699)">hi</p>',
			title="t",
			language="html",
		)
		self.assertTrue(html_to_docx(html))


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


class TestMarkdownAttrPropagation(unittest.TestCase):
	def test_tags_inside_fenced_code_are_ignored(self):
		src = (
			'<div class="a">\n<p>x</p>\n</div>\n\n```html\n<div markdown="1">demo</div>\n```\n'
		)
		self.assertEqual(_propagate_markdown_attr(src), src)

	def test_tags_inside_inline_code_are_ignored(self):
		src = '<div class="a">use `<b markdown="1">` here</div>'
		self.assertEqual(_propagate_markdown_attr(src), src)

	def test_existing_attr_not_duplicated(self):
		src = '<div markdown="1"><section markdown="1">## T</section></div>'
		out = _propagate_markdown_attr(src)
		self.assertEqual(out.count("markdown="), 2)

	def test_ancestor_gets_attr_once(self):
		src = '<div class="split"><section markdown="1">## T</section></div>'
		out = _propagate_markdown_attr(src)
		self.assertEqual(out.count("markdown="), 2)
		self.assertTrue(out.startswith('<div class="split" markdown="1">'))

	def test_unclosed_implicit_tags_do_not_mark_unrelated_ancestors(self):
		src = '<div class="outer"><p>open paragraph<ul><li>one<li>two</ul><div class="x" markdown="1">## T</div></div>'
		out = _propagate_markdown_attr(src)
		self.assertIn('<div class="outer" markdown="1">', out)
		self.assertNotIn('<p markdown', out)
		self.assertNotIn('<li markdown', out)
		self.assertNotIn('<ul markdown', out)

	def test_unclosed_paragraph_sibling_not_marked(self):
		src = '<div class="o"><p>dangling<div markdown="1">## T</div></div>'
		self.assertNotIn('<p markdown', _propagate_markdown_attr(src))

	def test_pretty_printed_children_are_dedented_not_code(self):
		src = (
			'<div class="split">\n'
			'    <section markdown="1">\n'
			'        ## Heading\n\n'
			'        | A | B |\n'
			'        |---|---|\n'
			'        | 1 | 2 |\n'
			'    </section>\n'
			'</div>\n'
		)
		html = render_document_html(src, language="html")
		self.assertIn("<h2>Heading</h2>", html)
		self.assertIn("<table>", html)
		self.assertNotIn("<pre><code>", html)

	def test_dedent_only_touches_markdown_containers(self):
		src = '<div>\n    <p>raw</p>\n</div>'
		self.assertEqual(_dedent_markdown_containers(src), src)


class TestDedentMarkdownContainers(unittest.TestCase):
	def test_nested_containers_dedent_outer_then_inner(self):
		src = (
			'<div markdown="1">\n'
			'    outer\n'
			'    <section markdown="1">\n'
			'        inner\n'
			'          deeper\n'
			'    </section>\n'
			'</div>\n'
		)
		self.assertEqual(
			_dedent_markdown_containers(src),
			'<div markdown="1">\n'
			'outer\n'
			'<section markdown="1">\n'
			'inner\n'
			'  deeper\n'
			'</section>\n'
			'</div>\n',
		)

	def test_pre_content_whitespace_preserved(self):
		src = (
			'<div markdown="1">\n'
			'    ## Title\n'
			'    <pre>\n'
			'        keep   indent\n'
			'    </pre>\n'
			'    after\n'
			'</div>'
		)
		out = _dedent_markdown_containers(src)
		self.assertIn('\n        keep   indent\n    </pre>', out)
		self.assertIn('\n## Title\n', out)
		self.assertIn('\nafter\n', out)

	def test_fenced_code_interior_preserved(self):
		src = (
			'<div markdown="1">\n'
			'    text\n'
			'    ```\n'
			'        code\n'
			'    ```\n'
			'</div>'
		)
		out = _dedent_markdown_containers(src)
		self.assertIn('\n        code\n', out)
		self.assertIn('\ntext\n```\n', out)

	def test_many_containers_are_fast(self):
		block = '<section markdown="1">\n    ## H\n\n    | A | B |\n    |---|---|\n    | 1 | 2 |\n</section>\n'
		src = "<div>\n" + block * 500 + "</div>\n"
		started = time.perf_counter()
		out = _dedent_markdown_containers(src)
		self.assertLess(time.perf_counter() - started, 1.0)
		self.assertIn("\n## H\n", out)

	def test_containers_beyond_cap_left_as_is(self):
		block = '<section markdown="1">\n    ## H\n</section>\n'
		out = _dedent_markdown_containers(block * 201)
		self.assertEqual(out.count("\n## H\n"), 200)
		self.assertEqual(out.count("\n    ## H\n"), 1)


class TestDedentLowFindings(unittest.TestCase):
	def test_in_ranges_bisect_matches_linear(self):
		ranges = [(5, 10), (20, 30), (40, 41)]
		for i in range(50):
			self.assertEqual(_in_ranges(i, ranges), any(lo < i < hi for lo, hi in ranges), i)

	def test_text_after_open_tag_does_not_block_dedent(self):
		src = '<div markdown="1">Intro\n    ## H\n    - a\n</div>'
		out = _dedent_markdown_containers(src)
		self.assertIn("Intro\n## H\n- a\n", out)

	def test_markdown_tag_inside_pre_is_not_a_container(self):
		src = '<pre>\n<div markdown="1">\n    x\n</div>\n</pre>\n'
		self.assertEqual(_markdown_containers(src), [])
		self.assertEqual(_dedent_markdown_containers(src), src)

	def test_markdown_tag_inside_fence_is_not_a_container(self):
		src = '```\n<div markdown="1">\n    x\n</div>\n```\n'
		self.assertEqual(_markdown_containers(src), [])


class TestRtlDocument(unittest.TestCase):
	ARABIC = "# \u062a\u0642\u0631\u064a\u0631 \u0627\u0644\u0627\u0633\u062a\u062f\u0627\u0645\u0629\n\n\u0646\u0635 \u0639\u0631\u0628\u064a.\n\n- \u0628\u0646\u062f \u0623\u0648\u0644\n\n> \u0627\u0642\u062a\u0628\u0627\u0633\n\n| \u0623 | \u0628 |\n|---|---|\n| 1 | 2 |\n"

	def test_logical_css_and_dir_present(self):
		html = render_document_html(self.ARABIC, title="t")
		self.assertIn('<body dir="auto">', html)
		for needle in ("padding-inline-start", "border-inline-start", "padding-inline-end", "text-align: start"):
			self.assertIn(needle, html)
		self.assertNotIn("padding: 4pt 8pt 4pt 0", html)
		self.assertIn("letter-spacing: normal !important", html)

	def test_arabic_renders_to_pdf_without_errors(self):
		try:
			from weasyprint import HTML
		except Exception:
			self.skipTest("WeasyPrint unavailable")
		pdf = HTML(string=render_document_html(self.ARABIC, title="t")).write_pdf()
		self.assertTrue(pdf.startswith(b"%PDF"))

	def test_arabic_renders_to_docx(self):
		data = html_to_docx(render_document_html(self.ARABIC, title="t"))
		self.assertTrue(zipfile.is_zipfile(BytesIO(data)))


class TestPreRegions(unittest.TestCase):
	def _contained(self, src):
		return _propagate_markdown_attr(src)

	def test_unclosed_pre_in_backticks_does_not_swallow_later_containers(self):
		src = 'Use `<pre>` for code.\n\n<div class="o"><section markdown="1">\n    ## T\n</section></div>\n'
		self.assertIn('<div class="o" markdown="1">', self._contained(src))
		self.assertIn("\n## T\n", _dedent_markdown_containers(src))

	def test_pre_inside_fenced_example_is_ignored(self):
		src = (
			'```html\n<pre>\n```\n\n'
			'<div class="o"><section markdown="1">\n    ## T\n</section></div>\n'
		)
		self.assertIn('<div class="o" markdown="1">', self._contained(src))
		self.assertIn("\n## T\n", _dedent_markdown_containers(src))

	def test_unclosed_bare_pre_is_literal(self):
		src = '<pre>\n\n<div class="o"><section markdown="1">\n    ## T\n</section></div>\n'
		self.assertIn('<div class="o" markdown="1">', self._contained(src))

	def test_real_pre_still_excluded(self):
		src = '<div markdown="1">\n    a\n    <pre>\n      keep\n    </pre>\n    b\n</div>\n'
		out = _dedent_markdown_containers(src)
		self.assertIn("\n      keep\n    </pre>", out)
		self.assertIn("\na\n", out)
		# a tag inside a real pre is not structural
		src2 = '<div class="o"><pre><section markdown="1">x</section></pre></div>'
		self.assertEqual(self._contained(src2), src2)

	def test_two_pre_blocks(self):
		src = (
			'<div markdown="1">\n    a\n    <pre>\n      one\n    </pre>\n'
			'    mid\n    <pre>\n      two\n    </pre>\n</div>\n'
		)
		out = _dedent_markdown_containers(src)
		self.assertIn("\n      one\n    </pre>", out)
		self.assertIn("\nmid\n", out)
		self.assertIn("\n      two\n    </pre>", out)


class TestPreBoundaries(unittest.TestCase):
	def test_custom_element_and_selfclosed_pre_are_not_regions(self):
		from huf.ai.artifacts.render.html import _pre_regions
		for src in ('<pre-foo>x</pre>', '<pre/>x</pre>', '<pre />x</pre>'):
			self.assertEqual(_pre_regions(src), [], src)
		self.assertEqual(_pre_regions('<pre-foo>a</pre-foo><pre>b</pre>'), [(20, 32)])

	def test_uppercase_and_attr_pre_are_regions(self):
		from huf.ai.artifacts.render.html import _pre_regions
		self.assertEqual(_pre_regions('<PRE>a</PRE>'), [(0, 12)])
		self.assertEqual(_pre_regions('<pre class="x">a</pre>'), [(0, 22)])

	def test_closer_boundary(self):
		from huf.ai.artifacts.render.html import _pre_regions
		self.assertEqual(_pre_regions('<pre>a</pre-x></pre >'), [(0, 21)])

	def test_container_after_closer_on_same_line_is_processed(self):
		src = '<pre>\n  x\n</pre><div class="o"><section markdown="1">\n    ## T\n</section></div>\n'
		self.assertIn('<div class="o" markdown="1">', _propagate_markdown_attr(src))
		self.assertIn("\n## T\n", _dedent_markdown_containers(src))
		src2 = '<div markdown="1">\n    <pre>\n      k\n    </pre><section markdown="1">\n        ## T\n    </section>\n</div>\n'
		out = _dedent_markdown_containers(src2)
		self.assertIn("\n      k\n", out)
		self.assertIn("\n## T\n", out)


class TestPreRegionsLinear(unittest.TestCase):
	def test_many_unterminated_pre_openers_are_fast(self):
		from huf.ai.artifacts.render.html import _pre_regions
		src = "<pre " * 5000
		start = time.time()
		_pre_regions(src)
		self.assertLess(time.time() - start, 1.0)


class TestLeakedMarkdownInHtmlLayouts(unittest.TestCase):
	"""Real failing documents: markdown inside HTML layout blocks must not render literally."""

	SPLIT = (
		'<div class="split">\n'
		'  <section class="split-main" markdown="1">\n\n'
		"  ## Operational Highlights\n\n"
		"  Our pivot.\n"
		"  * **Goal:** Understand the team.\n\n"
		"  </section>\n"
		'  <aside class="split-side" markdown="1">\n\n'
		"  #### Quick Checklist\n"
		"  * [ ] Equipment shipped\n"
		"  * [x] Invite sent\n\n"
		"  </aside>\n"
		"</div>\n"
	)

	@staticmethod
	def _text(html):
		body = html.split("<body", 1)[1]
		body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
		return re.sub(r"<[^>]+>", "", body)

	def _assert_clean(self, text):
		self.assertNotRegex(text, r"(?m)^\s*#{1,6}\s")
		self.assertNotIn("**", text)
		self.assertNotRegex(text, r"(?m)^\s*\*\s")
		self.assertNotIn("[ ]", text)

	def test_markdown_attr_honoured_in_markdown_language(self):
		for lang in ("markdown", "html"):
			out = render_document_html(self.SPLIT, "t", lang)
			self._assert_clean(self._text(out))
			self.assertIn("<h2>Operational Highlights</h2>", out)
			self.assertIn("☐ Equipment shipped", out)
			self.assertIn("☑ Invite sent", out)

	def test_list_glued_to_paragraph_becomes_list(self):
		out = render_document_html(self.SPLIT, "t", "html")
		self.assertIn("<li><strong>Goal:</strong> Understand the team.</li>", out)

	def test_unmarked_container_with_markdown_text_is_parsed(self):
		src = '<div class="callout">\n## Hi\n- **a:** b\n- c\n</div>\n<div class="metric">45 Days</div>'
		for lang in ("markdown", "html"):
			out = render_document_html(src, "t", lang)
			self._assert_clean(self._text(out))
			self.assertIn("<h2>Hi</h2>", out)
			self.assertIn('<div class="metric">45 Days</div>', out)

	def test_plain_html_container_untouched_and_code_ignored(self):
		src = '<div class="callout">Plain text only</div>\n\n```\n<div>\n## not a heading\n</div>\n```\n'
		out = render_document_html(src, "t", "markdown")
		self.assertIn('<div class="callout">Plain text only</div>', out)
		self.assertIn("## not a heading", out)


class TestInlinePhrasingTags(unittest.TestCase):
	"""b/i/u/s/mark/... survive sanitization; dangerous markup does not."""

	def test_bold_preserved_in_callout(self):
		out = render_document_html(
			'<div class="callout"><b>Executive Summary:</b> up 18%.</div>', "t", "html"
		)
		self.assertIn("<b>Executive Summary:</b>", out)

	def test_nested_b_i_and_other_inline_tags(self):
		out = render_document_html(
			"<p><b>x <i>y</i></b> <u>u</u> <mark>m</mark> H<sub>2</sub>O x<sup>2</sup> <kbd>k</kbd></p>",
			"t",
			"html",
		)
		for frag in ("<b>x <i>y</i></b>", "<u>u</u>", "<mark>m</mark>", "<sub>2</sub>", "<sup>2</sup>", "<kbd>k</kbd>"):
			self.assertIn(frag, out)

	def test_script_and_handlers_still_stripped(self):
		out = render_document_html(
			'<p><b onclick="x()">a</b><script>alert(1)</script><i onerror="y()">b</i>'
			'<iframe src="http://e"></iframe><svg onload="z()"></svg></p>',
			"t",
			"html",
		)
		for bad in ("<script", "onclick", "onerror", "onload", "<iframe", "<svg"):
			self.assertNotIn(bad, out)
		self.assertIn("<b>a</b>", out)

	def test_docx_has_bold_run_for_b(self):
		html = render_document_html(
			'<div class="callout"><b>Executive Summary:</b> ok <u>u</u> <mark>m</mark></div>',
			"t",
			"html",
		)
		body = _docx_part(html_to_docx(html), "word/document.xml")
		self.assertRegex(body, r"<w:b/>|<w:b w:val=\"1\"/>|<w:b w:val=\"true\"/>")
		self.assertIn("Executive Summary", body)


class TestCssEscapeBypass(unittest.TestCase):
	def test_escaped_remote_constructs_removed(self):
		from huf.ai.artifacts.render.html import _sanitize_css

		for css in (
			"a{background:u\\72l(http://evil/x)}",
			"@\\69mport 'http://evil/x.css';a{color:red}",
			'a{background:image-set("http://evil/p.gif" 1x)}',
		):
			out = _sanitize_css(css)
			self.assertNotIn("evil", out, css)
		self.assertIn("color:red", _sanitize_css("a{color:red}"))


	def test_decoded_escapes_cannot_break_out_of_style(self):
		from huf.ai.artifacts.render.html import _sanitize_css

		out = _sanitize_css('a{content:"\\3c /style\\3e \\3c script\\3e alert(1)\\3c /script\\3e"}u\\72l(http://evil/x)')
		self.assertNotIn("<", out)
		self.assertNotIn("evil", out)

	def test_legit_css_is_kept_verbatim(self):
		from huf.ai.artifacts.render.html import _sanitize_css

		for css in ('a::before{content:"\\A"}', "a::after{content:'//'}", 'a{content:"\\22 y"}'):
			self.assertEqual(_sanitize_css(css), css)
