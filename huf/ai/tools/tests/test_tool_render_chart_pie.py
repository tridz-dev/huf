# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Pie handling of the render_chart tool handler (pure templating, no site needed)."""

import unittest

from huf.ai.tools.render_tools import handle_render_chart


class TestRenderChartPie(unittest.TestCase):
	def test_pie_disables_animation(self):
		result = handle_render_chart(chart_type="pie", data=[{"label": "A", "value": 1}])
		self.assertIn("isAnimationActive={false}", result)

	def test_rejects_row_without_label(self):
		with self.assertRaises(ValueError) as ctx:
			handle_render_chart(chart_type="pie", data=[{"label": "A", "value": 1}, {"value": 2}])
		self.assertIn("data[1]", str(ctx.exception))
		self.assertIn("label", str(ctx.exception))

	def test_rejects_blank_label(self):
		with self.assertRaises(ValueError):
			handle_render_chart(chart_type="pie", data=[{"label": "", "value": 1}])

	def test_name_is_accepted_as_label_alias(self):
		result = handle_render_chart(chart_type="pie", data=[{"name": "Open", "value": 3}])
		self.assertIn('"label": "Open"', result)
