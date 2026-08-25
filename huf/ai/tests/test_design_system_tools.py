# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Tests for huf.ai.tools.render_tools — list_app_components/render_app_component,
the design-system-aware component rendering tools. Mirrors the shape and
escaping-regression pattern of test_render_tools.py.

huf.ai.tools.render_tools has no frappe dependency (pure string/structural
templating), so this module runs as plain unittest with no bench/site
required.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_design_system_tools
"""

import unittest

from huf.ai.tools.render_tools import (
	APP_COMPONENT_ALLOWLIST,
	handle_list_app_components,
	handle_render_app_component,
)


class TestListAppComponents(unittest.TestCase):
	def test_returns_non_empty_list_of_component_entries(self):
		components = handle_list_app_components()

		self.assertIsInstance(components, list)
		self.assertGreater(len(components), 0)

		for entry in components:
			self.assertIn("name", entry)
			self.assertIn("props", entry)
			self.assertIn("example", entry)
			self.assertIn(entry["name"], APP_COMPONENT_ALLOWLIST)

	def test_includes_a_known_common_component(self):
		names = {entry["name"] for entry in handle_list_app_components()}
		self.assertIn("Button", names)
		self.assertIn("Card", names)


class TestRenderAppComponent(unittest.TestCase):
	def test_rejects_unknown_component_name(self):
		with self.assertRaises(ValueError) as ctx:
			handle_render_app_component(component="NotARealComponent", props={}, confirm=True)
		self.assertIn("NotARealComponent", str(ctx.exception))
		self.assertIn("allowed design-system components", str(ctx.exception))

	def test_confirm_false_returns_preview_without_confirm_required_false(self):
		result = handle_render_app_component(component="Badge", props={"variant": "secondary"}, confirm=False)

		self.assertFalse(result["rendered"])
		self.assertTrue(result["confirm_required"])
		self.assertIn("<artifact", result["artifact"])
		self.assertIn("Badge", result["artifact"])

	def test_confirm_true_returns_rendered_artifact(self):
		result = handle_render_app_component(component="Badge", props={"variant": "secondary"}, confirm=True)

		self.assertTrue(result["rendered"])
		self.assertFalse(result["confirm_required"])
		self.assertTrue(result["artifact"].startswith('<artifact type="chart" language="jsx"'))
		self.assertTrue(result["artifact"].endswith("</artifact>"))
		self.assertIn('variant="secondary"', result["artifact"])

	def test_escapes_prop_value_containing_a_double_quote(self):
		# Regression test mirroring test_render_tools.py's escaping coverage:
		# a prop value containing a double-quote must not be able to close the
		# JSX attribute early and inject additional attributes/props.
		result = handle_render_app_component(
			component="Badge",
			props={"variant": 'secondary" onClick="evil()'},
			confirm=True,
		)

		artifact = result["artifact"]
		# The raw double-quote must not survive into the templated attribute.
		self.assertNotIn('variant="secondary" onClick="evil()"', artifact)
		# _escape_jsx_attr replaces '"' with "'", so the escaped form should
		# appear instead, and the injected onClick must not become a real
		# second JSX attribute.
		self.assertNotIn('onClick="evil()"', artifact)

	def test_defaults_props_to_empty_object_when_omitted(self):
		result = handle_render_app_component(component="Progress", confirm=True)
		self.assertEqual(result["artifact"].count("<Progress"), 1)

	def test_rejects_non_dict_props(self):
		with self.assertRaises(ValueError):
			handle_render_app_component(component="Progress", props="not-a-dict", confirm=True)


if __name__ == "__main__":
	unittest.main()
