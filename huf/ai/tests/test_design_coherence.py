# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""HTML (so PDF and the Document view) and DOCX are drawn from one design system."""

import re
import unittest

from huf.ai.artifacts.render import design_tokens as tokens
from huf.ai.artifacts.render import docx as docx_render
from huf.ai.artifacts.render import html as html_render


class TestDesignCoherence(unittest.TestCase):
	def test_docx_reads_the_shared_tokens(self):
		self.assertEqual(docx_render.BODY_FONT, tokens.BODY_FONT)
		self.assertEqual(docx_render.HEADING_FONT, tokens.HEADING_FONT)
		self.assertEqual(docx_render.MONO_FONT, tokens.MONO_FONT)
		self.assertEqual(docx_render._HEADING_SIZES_PT, tokens.HEADING_SIZES_PT)

	def test_html_stylesheet_uses_the_same_faces_first(self):
		css = html_render.PRINT_STYLESHEET_RESOLVED if hasattr(html_render, "PRINT_STYLESHEET_RESOLVED") else None
		if css is None:
			css = html_render.render_document_html("# T\n\ntext `c`", title="T")
		self.assertIn(f"'{tokens.BODY_FONT}'", css)
		self.assertIn(f"'{tokens.HEADING_FONT}'", css)
		self.assertIn(f"'{tokens.MONO_FONT}'", css)

	def test_html_heading_sizes_equal_the_token_scale(self):
		css = html_render.render_document_html("# T", title="T")
		for level, pt in tokens.HEADING_SIZES_PT.items():
			m = re.search(r"\bh%d\s*\{[^}]*?font-size:\s*([\d.]+)pt" % level, css)
			self.assertIsNotNone(m, f"h{level} size missing")
			self.assertEqual(float(m.group(1)), float(pt), f"h{level}")

	def test_metric_webfonts_are_loaded(self):
		css = html_render.render_document_html("# T", title="T")
		for family in tokens.METRIC_WEBFONTS:
			self.assertIn(family.replace(" ", "+"), css)
