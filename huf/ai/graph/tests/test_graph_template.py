"""``{"$template": ..., "vars": {...}}`` reference form (string templating) on GraphContext.resolve."""

import unittest

from huf.ai.graph.executor import GraphContext
from huf.ai.graph.templates import MAX_RENDERED_CHARS, TemplateError, render_template


class TestRender(unittest.TestCase):
	def test_basic(self):
		self.assertEqual(render_template("Refund logged for #{order}", {"order": "4521"}), "Refund logged for #4521")

	def test_escaped_braces(self):
		self.assertEqual(render_template("{{literal}} {x}", {"x": 1}), "{literal} 1")

	def test_types(self):
		out = render_template("{a}|{b}|{c}|{d}|{e}", {"a": True, "b": 1.5, "c": None, "d": [1], "e": {"k": "v"}})
		self.assertEqual(out, "true|1.5||1 item: 1|K: v")  # lists and objects become a short summary, never JSON

	def test_objects_never_pasted_as_json(self):
		order = {"customer": {"name": "Ada Lovelace"}, "total": 450, "items": [{"name": "A"}, {"name": "B"}, {"name": "C"}]}
		out = render_template("Order: {o}", {"o": order})
		self.assertEqual(out, "Order: Customer: Ada Lovelace, Total: 450, Items: 3 items: A, B and 1 more")
		for junk in ('{"', "[{", '":', "'"):
			self.assertNotIn(junk, out)

	def test_json_mode_for_model_text(self):
		self.assertEqual(render_template("{d}", {"d": {"k": "v"}}, objects="json"), '{"k": "v"}')

	def test_undefined_var_raises(self):
		with self.assertRaisesRegex(TemplateError, r"uses \{nope\} but no data was chosen"):
			render_template("hi {nope}", {})

	def test_malformed_raises(self):
		for bad in ("a { b", "a } b", "{}", "{1x}", "{a.b}"):
			with self.assertRaises(TemplateError, msg=bad):
				render_template(bad, {"a": 1})

	def test_value_braces_not_reinterpreted(self):
		self.assertEqual(render_template("{x}", {"x": "{y}"}), "{y}")

	def test_output_capped(self):
		with self.assertRaises(TemplateError):
			render_template("{x}", {"x": "a" * (MAX_RENDERED_CHARS + 1)})


class TestResolve(unittest.TestCase):
	def test_template_with_from_vars(self):
		ctx = GraphContext({"order": "88"})
		node = {"$template": "Refund for #{n}", "vars": {"n": {"$from": "context.order"}}}
		self.assertEqual(ctx.resolve(node), "Refund for #88")

	def test_missing_reference_renders_empty(self):
		ctx = GraphContext({})
		self.assertEqual(ctx.resolve({"$template": "[{n}]", "vars": {"n": {"$from": "context.zip"}}}), "[]")

	def test_nested_in_structures(self):
		ctx = GraphContext({"o": 5})
		out = ctx.resolve({"to": "x", "body": {"$template": "#{o}", "vars": {"o": {"$from": "context.o"}}}})
		self.assertEqual(out, {"to": "x", "body": "#5"})

	def test_no_vars(self):
		self.assertEqual(GraphContext({}).resolve({"$template": "plain {{x}}"}), "plain {x}")

	def test_undefined_var_raises_from_resolve(self):
		with self.assertRaises(TemplateError):
			GraphContext({}).resolve({"$template": "{x}", "vars": {}})

	def test_non_string_template_is_plain_dict(self):
		self.assertEqual(GraphContext({}).resolve({"$template": 3, "vars": {}}), {"$template": 3, "vars": {}})


class TestSummaryMarkers(unittest.TestCase):
	"""The "Use data" picker asks for a wording of a list or object through the variable-name prefix (UX-9)."""

	order = {"customer": "Ada Lovelace", "total": 450, "status": "paid"}

	def test_table_prefix_writes_rows_one_per_line(self):
		out = render_template("{table_order}", {"table_order": self.order})
		self.assertEqual(out.splitlines(), ["Customer: Ada Lovelace", "Total: 450", "Status: paid"])
		self.assertNotIn("{", out)

	def test_joined_prefix_joins_items_with_commas(self):
		self.assertEqual(render_template("Items: {joined_items}", {"joined_items": ["Tea", "Cake", "Jam"]}), "Items: Tea, Cake, Jam")
		self.assertEqual(render_template("{joined_items}", {"joined_items": [{"name": "A"}, {"name": "B"}]}), "A, B")

	def test_count_prefix_counts_items(self):
		self.assertEqual(render_template("{count_items} items", {"count_items": [1, 2, 3]}), "3 items")

	def test_prefix_on_a_plain_value_changes_nothing(self):
		self.assertEqual(render_template("{count_orders}|{table_x}|{joined_y}", {"count_orders": 7, "table_x": "t", "joined_y": "j"}), "7|t|j")

	def test_resolve_applies_markers_for_a_reference(self):
		ctx = GraphContext({"trigger_x": 1})
		ctx.record_output("n1", {"items": [{"name": "A"}, {"name": "B"}]})
		value = {"$template": "Bought {joined_items} ({count_items})", "vars": {"joined_items": {"$from": "n1.items"}, "count_items": {"$from": "n1.items"}}}
		self.assertEqual(ctx.resolve(value), "Bought A, B (2)")


if __name__ == "__main__":
	unittest.main()
