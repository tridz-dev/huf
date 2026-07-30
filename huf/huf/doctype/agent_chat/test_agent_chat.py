# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

from frappe.tests import IntegrationTestCase

from huf.ai.agent_chat import render_markdown


class TestAgentChat(IntegrationTestCase):
	def test_render_markdown(self):
		# Regression test: `from frappe.utils.markdown import markdown` is not
		# a valid import path on Frappe v16 — render_markdown() silently fell
		# back to returning raw, unrendered text.
		html = render_markdown("**bold**")

		self.assertIn("<strong>bold</strong>", html)
